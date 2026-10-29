import io
import json
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from model_registry.models import Model

pytestmark = pytest.mark.django_db

VALID_YAML = """
name: test_model
framework: sklearn
python_version: "3.12"
requirements: requirements.txt
model_artifact: model.pkl
task_type: regression
""".strip()

VALID_FILES = {
    "model.yaml": VALID_YAML,
    "requirements.txt": "scikit-learn==1.8.0\n",
    "model.pkl": "dummy-model",
}


def _zip_bytes(files: dict[str, str]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return bio.getvalue()


def _upload(client, files: dict[str, str] | None = None, name: str = "bundle.zip"):
    upload = SimpleUploadedFile(
        name, _zip_bytes(files or VALID_FILES), content_type="application/zip"
    )
    return client.post("/api/models/upload/", {"file": upload}, format="multipart")


@pytest.fixture
def approved_client(auth_client, user):
    user.can_upload_models = True
    user.save(update_fields=["can_upload_models"])
    return auth_client


@pytest.fixture
def staff_client(auth_client, user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return auth_client


# --- SEC-03: upload approval policy -----------------------------------------


def test_upload_requires_auth(api_client):
    res = _upload(api_client)

    assert res.status_code == 401


def test_upload_rejected_for_unapproved_user(auth_client):
    res = _upload(auth_client)

    assert res.status_code == 403
    assert res.data["code"] == "UPLOAD_NOT_APPROVED"
    assert not Model.objects.exists()


def test_approval_gate_runs_before_the_archive_is_read(auth_client):
    res = _upload(auth_client, name="bad.txt")

    assert res.status_code == 403
    assert not Model.objects.exists()


def test_upload_allowed_for_approved_user(approved_client, user):
    res = _upload(approved_client)

    assert res.status_code == 201
    model = Model.objects.get(id=res.data["model_id"])
    assert model.owner_id == user.id


def test_upload_allowed_for_staff_user(staff_client):
    res = _upload(staff_client)

    assert res.status_code == 201


@override_settings(UPLOAD_APPROVAL_REQUIRED=False)
def test_upload_allowed_when_policy_is_disabled(auth_client):
    res = _upload(auth_client)

    assert res.status_code == 201


# --- Upload validation -------------------------------------------------------


def test_upload_rejects_non_zip(approved_client):
    res = _upload(approved_client, name="bad.txt")

    assert res.status_code == 400


def test_upload_missing_model_yaml(approved_client):
    res = _upload(approved_client, files={"requirements.txt": "scikit-learn==1.8.0\n"})

    assert res.status_code == 400


class SpyS3:
    """Records the objects an upload would create."""

    def __init__(self):
        self.uploads: list[str] = []

    def upload_file(self, local_path, bucket, key):
        self.uploads.append(key)

    def list_objects_v2(self, *args, **kwargs):
        return {}

    def delete_objects(self, *args, **kwargs):
        return None


@pytest.fixture
def spy_s3(monkeypatch):
    spy = SpyS3()
    monkeypatch.setattr("model_registry.views.get_s3_client", lambda: spy)
    return spy


# --- SEC-04: archive limits --------------------------------------------------


def test_upload_rejects_path_traversal_entry(approved_client, spy_s3):
    files = dict(VALID_FILES)
    files["../escaped.txt"] = "boom"

    res = _upload(approved_client, files=files)

    assert res.status_code == 400
    assert spy_s3.uploads == []
    assert not Model.objects.exists()


def test_upload_rejects_absolute_path_entry(approved_client, spy_s3):
    files = dict(VALID_FILES)
    files["/etc/passwd"] = "boom"

    res = _upload(approved_client, files=files)

    assert res.status_code == 400
    assert spy_s3.uploads == []
    assert not Model.objects.exists()


def test_upload_rejects_manifest_path_outside_the_bundle(approved_client, spy_s3):
    files = dict(VALID_FILES)
    files["model.yaml"] = VALID_YAML.replace(
        "requirements: requirements.txt", "requirements: ../../etc/passwd"
    )

    res = _upload(approved_client, files=files)

    assert res.status_code == 400
    assert spy_s3.uploads == []
    assert not Model.objects.exists()


def test_upload_rejects_an_expansion_bomb(approved_client, spy_s3):
    files = dict(VALID_FILES)
    files["bomb.bin"] = "\0" * 5_000_000  # compresses far beyond the default 100x limit

    res = _upload(approved_client, files=files)

    assert res.status_code == 400
    assert spy_s3.uploads == []
    assert not Model.objects.exists()


def test_upload_failure_returns_a_safe_envelope(approved_client, monkeypatch, caplog):
    """SEC-06: internal failure details stay in the log, not in the response."""

    def explode():
        raise RuntimeError(
            "boto3 S3 upload failed for key model/x: AccessDenied (access key AKIAEXAMPLE)"
        )

    monkeypatch.setattr("model_registry.views.get_s3_client", explode)

    with caplog.at_level("ERROR", logger="core.errors"):
        res = _upload(approved_client)

    assert res.status_code == 500
    assert res.data["code"] == "UPLOAD_FAILED"
    assert res.data["request_id"]
    body = json.dumps(res.data)
    assert "AKIAEXAMPLE" not in body
    assert "boto3" not in body
    assert "AccessDenied" not in body
    assert not Model.objects.exists()
    # The details are retained server-side with the same correlation id.
    assert "AccessDenied" in caplog.text
    error_record = next(
        record for record in caplog.records if record.name == "core.errors"
    )
    assert error_record.request_id == res.data["request_id"]


@override_settings(THROTTLING_ENABLED=True)
def test_upload_is_rate_limited(approved_client, monkeypatch):
    from django.core.cache import cache

    from core.throttling import ConfigurableScopedRateThrottle

    monkeypatch.setattr(
        ConfigurableScopedRateThrottle, "THROTTLE_RATES", {"upload": "2/min"}
    )
    cache.clear()
    try:
        codes = []
        for index in range(3):
            files = dict(VALID_FILES)
            files["model.yaml"] = VALID_YAML.replace(
                "name: test_model", f"name: rate_model_{index}"
            )
            codes.append(_upload(approved_client, files=files).status_code)
        assert codes == [201, 201, 429]
    finally:
        cache.clear()


def test_upload_success_and_owner_is_request_user(approved_client, user):
    res = _upload(approved_client)

    assert res.status_code == 201

    model_id = res.data["model_id"]
    assert "model_version_id" in res.data
    m = Model.objects.get(id=model_id)
    assert m.owner_id == user.id
