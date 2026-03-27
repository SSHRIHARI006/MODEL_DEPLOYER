import io
import zipfile
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from deployments.models import Deployment
from model_registry.models import Model

pytestmark = pytest.mark.django_db


def _zip_bytes(files: dict[str, str]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return bio.getvalue()


def test_full_flow_register_login_upload_key_predict(api_client, monkeypatch):
    class DummyResponse:
        status_code = 200
        content = b"{}"

        @staticmethod
        def json():
            return {"prediction": [9.99]}

    monkeypatch.setattr("prediction_gateway.views.requests.post", lambda *args, **kwargs: DummyResponse())

    reg = api_client.post(
        "/api/auth/register/",
        {"email": "flow@example.com", "password": "TestPass123!"},
        format="json",
    )
    assert reg.status_code in (200, 201)

    login = api_client.post(
        "/api/auth/login/",
        {"email": "flow@example.com", "password": "TestPass123!"},
        format="json",
    )
    assert login.status_code == 200
    token = login.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

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
    up = api_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert up.status_code == 201
    model_id = up.data["model_id"]

    key_res = api_client.post("/api/keys/", {"model_id": model_id, "name": "flow-key"}, format="json")
    assert key_res.status_code == 201
    api_key = key_res.data["key"]

    model = Model.objects.get(id=model_id)
    version = model.versions.order_by("-created_at").first()
    Deployment.objects.create(
        model_version=version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_X_API_KEY=api_key,
    )
    pred = api_client.post(f"/api/predict/{model_id}/", {"input": [4]}, format="json")
    assert pred.status_code == 200
    assert "prediction" in pred.data