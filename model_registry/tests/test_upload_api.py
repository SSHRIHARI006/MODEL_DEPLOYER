import io
import zipfile
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from model_registry.models import Model

pytestmark = pytest.mark.django_db


def _zip_bytes(files: dict[str, str]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return bio.getvalue()


def test_upload_requires_auth(api_client):
    data = _zip_bytes(
        {
            "model.yaml": "framework: sklearn\npython_version: '3.12'\nrequirements: requirements.txt\nmodel_artifact: model.pkl\n"
        }
    )
    upload = SimpleUploadedFile("bundle.zip", data, content_type="application/zip")
    res = api_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 401


def test_upload_rejects_non_zip(auth_client):
    upload = SimpleUploadedFile("bad.txt", b"hello", content_type="text/plain")
    res = auth_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 400


def test_upload_missing_model_yaml(auth_client):
    data = _zip_bytes({"requirements.txt": "scikit-learn==1.8.0\n"})
    upload = SimpleUploadedFile("bundle.zip", data, content_type="application/zip")
    res = auth_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 400


def test_upload_success_and_owner_is_request_user(auth_client, user):
    yaml_content = """
name: test_model
framework: sklearn
python_version: "3.12"
requirements: requirements.txt
model_artifact: model.pkl
task_type: regression
""".strip()

    data = _zip_bytes(
        {
            "model.yaml": yaml_content,
            "requirements.txt": "scikit-learn==1.8.0\n",
            "model.pkl": "dummy-model",
        }
    )
    upload = SimpleUploadedFile("bundle.zip", data, content_type="application/zip")

    res = auth_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 201

    model_id = res.data["model_id"]
    assert "model_version_id" in res.data
    m = Model.objects.get(id=model_id)
    assert m.owner_id == user.id
