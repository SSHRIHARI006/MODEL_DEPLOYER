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
    data = _zip_bytes({"model.yaml": "model:\n  name: m\n  framework: sklearn\n  task: regression\nruntime:\n  entry_point: pipeline.py\nartifacts:\n  model_file: model.pkl\n"})
    upload = SimpleUploadedFile("bundle.zip", data, content_type="application/zip")
    res = api_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 401


def test_upload_rejects_non_zip(auth_client):
    upload = SimpleUploadedFile("bad.txt", b"hello", content_type="text/plain")
    res = auth_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 400


def test_upload_missing_model_yaml(auth_client):
    data = _zip_bytes({"pipeline.py": "def predict(data, model_path):\n    return [1]\n"})
    upload = SimpleUploadedFile("bundle.zip", data, content_type="application/zip")
    res = auth_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 400


def test_upload_success_and_owner_is_request_user(auth_client, user):
    yaml_content = """
model:
  name: test_model
  framework: sklearn
  task: regression
runtime:
  entry_point: pipeline.py
  predict_function: predict
artifacts:
  model_file: model.pkl
""".strip()

    data = _zip_bytes(
        {
            "model.yaml": yaml_content,
            "pipeline.py": "def predict(data, model_path):\n    return [1]\n",
            "schema.json": '{"type":"object","properties":{"input":{"type":"array"}},"required":["input"]}',
        }
    )
    upload = SimpleUploadedFile("bundle.zip", data, content_type="application/zip")

    res = auth_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 201

    model_id = res.data["model_id"]
    m = Model.objects.get(id=model_id)
    assert m.owner_id == user.id