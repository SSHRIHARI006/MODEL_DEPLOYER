import io
import zipfile
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from deployments.models import Deployment
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db


def _zip_bytes(files: dict[str, str]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return bio.getvalue()


def test_full_flow_register_login_upload_key_predict(api_client, monkeypatch):
    class DummyRunner:
        def predict(self, payload):
            return RunnerResult(status_code=200, data={"predictions": [9.99]})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: DummyRunner(),
    )

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
    up = api_client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert up.status_code == 201
    model_id = up.data["model_id"]
    model_version_id = up.data["model_version_id"]

    key_res = api_client.post(
        "/api/keys/", {"model_id": model_id, "name": "flow-key"}, format="json"
    )
    assert key_res.status_code == 201
    api_key = key_res.data["key"]

    Deployment.objects.create(
        model_version_id=model_version_id,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_X_API_KEY=api_key,
    )
    pred = api_client.post(
        f"/api/predict/{model_id}/",
        {"instances": [{"feature_a": 1.2, "feature_b": 0.5}]},
        format="json",
    )
    assert pred.status_code == 200
    assert "predictions" in pred.data
