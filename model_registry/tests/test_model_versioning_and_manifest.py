import io
import json
import zipfile
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from deployments.models import Deployment
from model_registry.manifest import (
    ManifestValidationError,
    validate_bundle_files,
    validate_manifest,
    validate_prediction_instances,
)
from model_registry.models import Model, ModelVersion
from model_registry.views import get_next_version

pytestmark = pytest.mark.django_db


def _make_zip(files: dict[str, str]) -> SimpleUploadedFile:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return SimpleUploadedFile("bundle.zip", bio.getvalue(), content_type="application/zip")


class SpyS3:
    def __init__(self):
        self.uploads = []
        self.deleted_prefixes = []

    def upload_file(self, local_path, bucket, key):
        self.uploads.append((bucket, key))

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, **kwargs):
        return []

    def list_objects_v2(self, *args, **kwargs):
        return {}

    def delete_objects(self, *args, **kwargs):
        return None


@pytest.fixture
def spy_s3(monkeypatch):
    spy = SpyS3()
    monkeypatch.setattr("model_registry.views.get_s3_client", lambda: spy)
    return spy


# ---------------------------------------------------------------------------
# API-01: Manifest & Bundle Schema Validation
# ---------------------------------------------------------------------------


def test_validate_manifest_valid():
    manifest = {
        "name": "my-model",
        "framework": "sklearn",
        "python_version": "3.12",
        "requirements": "requirements.txt",
        "model_artifact": "model.pkl",
        "task_type": "classification",
        "input_type": "tabular",
    }
    validate_manifest(manifest)  # Should not raise


def test_validate_manifest_unsupported_framework():
    manifest = {
        "framework": "xgboost_custom",
        "python_version": "3.12",
        "requirements": "requirements.txt",
        "model_artifact": "model.pkl",
    }
    with pytest.raises(ManifestValidationError) as exc:
        validate_manifest(manifest)
    assert exc.value.code == "INVALID_MANIFEST"
    assert "framework" in str(exc.value)


def test_validate_manifest_unsupported_python_version():
    manifest = {
        "framework": "sklearn",
        "python_version": "2.7",
        "requirements": "requirements.txt",
        "model_artifact": "model.pkl",
    }
    with pytest.raises(ManifestValidationError) as exc:
        validate_manifest(manifest)
    assert exc.value.code == "INVALID_MANIFEST"


def test_validate_manifest_state_dict_requires_class_file(tmp_path):
    manifest = {
        "framework": "pytorch",
        "python_version": "3.12",
        "requirements": "requirements.txt",
        "model_artifact": "model.pt",
        "load_method": "state_dict",
    }
    validate_manifest(manifest)
    # Bundle check requires class file
    (tmp_path / "requirements.txt").write_text("torch\n")
    (tmp_path / "model.pt").write_bytes(b"dummy")
    with pytest.raises(ManifestValidationError) as exc:
        validate_bundle_files(tmp_path, manifest)
    assert exc.value.code == "MISSING_CLASS_FILE"


def test_validate_prediction_instances_consistency():
    # Valid dict instances with matching keys
    validate_prediction_instances([{"a": 1, "b": 2}, {"a": 3, "b": 4}])

    # Inconsistent dict keys
    with pytest.raises(ValueError, match="mismatched keys"):
        validate_prediction_instances([{"a": 1, "b": 2}, {"a": 3, "c": 4}])

    # Valid array instances with matching lengths
    validate_prediction_instances([[1, 2, 3], [4, 5, 6]])

    # Inconsistent array lengths
    with pytest.raises(ValueError, match="mismatched length"):
        validate_prediction_instances([[1, 2, 3], [4, 5]])

    # Empty array
    with pytest.raises(ValueError, match="non-empty array"):
        validate_prediction_instances([])


# ---------------------------------------------------------------------------
# API-02: Versioning Workflow
# ---------------------------------------------------------------------------


def test_get_next_version(user):
    model = Model.objects.create(name="versioned-model", framework="sklearn", owner=user)
    assert get_next_version(model) == "v1"

    ModelVersion.objects.create(model=model, version="v1", artifact_path="s3://b/1/v1")
    assert get_next_version(model) == "v2"

    ModelVersion.objects.create(model=model, version="v2", artifact_path="s3://b/1/v2")
    assert get_next_version(model) == "v3"


def test_version_upload_and_listing(auth_client, user, spy_s3):
    user.can_upload_models = True
    user.save(update_fields=["can_upload_models"])

    # Create initial model and v1
    model = Model.objects.create(name="test-model", framework="sklearn", owner=user)
    v1 = ModelVersion.objects.create(model=model, version="v1", artifact_path="s3://bucket/m/v1")

    # Upload v2
    files = {
        "model.yaml": "framework: sklearn\npython_version: '3.12'\nrequirements: req.txt\nmodel_artifact: model.pkl\n",
        "req.txt": "scikit-learn\n",
        "model.pkl": "weights-v2",
        "schema.json": json.dumps({"type": "array", "items": {"type": "number"}}),
    }
    upload = _make_zip(files)

    res = auth_client.post(f"/api/models/{model.id}/versions/", {"file": upload}, format="multipart")
    assert res.status_code == 201
    assert res.data["version"] == "v2"
    assert res.data["model_id"] == str(model.id)

    # Verify both versions exist
    v2 = ModelVersion.objects.get(model=model, version="v2")
    assert v2.status == "READY"
    assert "schema.json" in v2.schema_path

    # List versions
    list_res = auth_client.get(f"/api/models/{model.id}/versions/")
    assert list_res.status_code == 200
    assert len(list_res.data["versions"]) == 2
    assert [v["version"] for v in list_res.data["versions"]] == ["v1", "v2"]


def test_version_delete_prevented_when_active_deployments(auth_client, user, spy_s3):
    model = Model.objects.create(name="active-model", framework="sklearn", owner=user)
    v1 = ModelVersion.objects.create(model=model, version="v1", artifact_path="s3://bucket/m/v1")

    dep = Deployment.objects.create(
        model_version=v1,
        status=Deployment.Status.RUNNING,
    )

    # Attempt to delete v1 should fail with 409 Conflict
    res = auth_client.delete(f"/api/models/{model.id}/versions/v1/")
    assert res.status_code == 409
    assert res.data["code"] == "VERSION_IN_USE"
    assert ModelVersion.objects.filter(id=v1.id).exists()

    # Once stopped, delete succeeds
    dep.status = Deployment.Status.STOPPED
    dep.save(update_fields=["status"])

    del_res = auth_client.delete(f"/api/models/{model.id}/versions/v1/")
    assert del_res.status_code == 200
    assert not ModelVersion.objects.filter(id=v1.id).exists()


def test_version_artifact_delete_failure_keeps_database_version(auth_client, user, monkeypatch):
    model = Model.objects.create(name="storage-error-model", framework="sklearn", owner=user)
    version = ModelVersion.objects.create(
        model=model,
        version="v1",
        artifact_path="s3://bucket/model/v1",
    )
    monkeypatch.setattr(
        "model_registry.views.get_s3_client",
        lambda: object(),
    )
    monkeypatch.setattr(
        "model_registry.views.delete_prefix_paginated",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )

    res = auth_client.delete(f"/api/models/{model.id}/versions/v1/")

    assert res.status_code == 500
    assert ModelVersion.objects.filter(id=version.id).exists()


def test_version_deletion_does_not_delete_other_versions(auth_client, user, monkeypatch):
    model = Model.objects.create(name="isolated-version-model", framework="sklearn", owner=user)
    v1 = ModelVersion.objects.create(model=model, version="v1", artifact_path="s3://bucket/model/v1")
    v2 = ModelVersion.objects.create(model=model, version="v2", artifact_path="s3://bucket/model/v2")
    deleted = []
    monkeypatch.setattr("model_registry.views.get_s3_client", lambda: object())
    monkeypatch.setattr(
        "model_registry.views.delete_prefix_paginated",
        lambda client, bucket, prefix: deleted.append(prefix),
    )

    res = auth_client.delete(f"/api/models/{model.id}/versions/v1/")

    assert res.status_code == 200
    assert deleted == [f"{model.id}/v1/"]
    assert not ModelVersion.objects.filter(id=v1.id).exists()
    assert ModelVersion.objects.filter(id=v2.id).exists()
