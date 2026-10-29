from __future__ import annotations

import io
import zipfile
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from deployments.models import Deployment
from runners.base import RunnerResult

User = get_user_model()
pytestmark = pytest.mark.django_db

def make_zip(files: dict[str, str | bytes]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if isinstance(content, str):
                zf.writestr(name, content.encode("utf-8"))
            else:
                zf.writestr(name, content)
    return bio.getvalue()


@pytest.fixture
def uploader_client(api_client, db):
    user = User.objects.create_user(
        email="pipeline_tester@example.com",
        username="pipelinetester",
        password="TestPass123!",
        can_upload_models=True,
    )
    res = api_client.post(
        "/api/auth/login/",
        {"email": "pipeline_tester@example.com", "password": "TestPass123!"},
        format="json",
    )
    token = res.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client, user


def test_sklearn_pipeline_upload_deploy_predict(uploader_client, monkeypatch):
    """3D: Sklearn pipeline test from upload to deploy to predict and cache verification."""
    client, user = uploader_client

    # Provide a mock runner for prediction gateway
    class FakeSklearnRunner:
        def readiness(self):
            return RunnerResult(status_code=200, data={"status": "ready"})

        def predict(self, payload):
            instances = payload.get("instances", [])
            # Predict known linear sum for instances
            preds = [float(sum(inst.values())) for inst in instances]
            return RunnerResult(status_code=200, data={"predictions": preds})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: FakeSklearnRunner(),
    )

    file_content = make_zip(
        {
            "model.yaml": """
name: integration-sklearn
framework: sklearn
python_version: "3.12"
requirements: requirements.txt
model_artifact: model.pkl
task_type: regression
""".strip(),
            "requirements.txt": "scikit-learn==1.8.0\n",
            "model.pkl": b"fixture-artifact",
        }
    )

    upload = SimpleUploadedFile("01_linear_regression.zip", file_content, content_type="application/zip")
    res_up = client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res_up.status_code == 201
    model_id = res_up.data["model_id"]
    model_version_id = res_up.data["model_version_id"]

    # Create model key
    res_key = client.post("/api/keys/", {"model_id": model_id, "name": "test-key"}, format="json")
    assert res_key.status_code == 201
    api_key = res_key.data["key"]

    # Create active deployment
    dep = Deployment.objects.create(
        model_version_id=model_version_id,
        status=Deployment.Status.RUNNING,
        internal_url="http://runner:8001",
    )

    # First prediction (cache miss)
    client.credentials(
        HTTP_AUTHORIZATION=client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key,
    )
    payload = {"instances": [{"f1": 1.0, "f2": 2.0, "f3": 3.0, "f4": 4.0}]}
    pred_res1 = client.post(f"/api/predict/{model_id}/", payload, format="json")
    assert pred_res1.status_code == 200
    assert pred_res1.data["predictions"] == [10.0]

    # Second prediction (cache hit or identical result)
    pred_res2 = client.post(f"/api/predict/{model_id}/", payload, format="json")
    assert pred_res2.status_code == 200
    assert pred_res2.data["predictions"] == pred_res1.data["predictions"]


def test_pytorch_pipeline_upload_deploy_predict(uploader_client, monkeypatch):
    """3D: PyTorch pipeline test from upload to deploy to predict."""
    client, user = uploader_client

    class FakePyTorchRunner:
        def readiness(self):
            return RunnerResult(status_code=200, data={"status": "ready"})

        def predict(self, payload):
            instances = payload.get("instances", [])
            preds = [float(sum(inst.values())) if isinstance(inst, dict) else float(sum(inst)) for inst in instances]
            return RunnerResult(status_code=200, data={"predictions": preds})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: FakePyTorchRunner(),
    )

    file_content = make_zip(
        {
            "model.yaml": """
name: integration-pytorch
framework: pytorch
python_version: "3.12"
requirements: requirements.txt
model_artifact: model.pt
task_type: regression
""".strip(),
            "requirements.txt": "torch==2.12.0+cpu\n",
            "model.pt": b"fixture-artifact",
        }
    )

    upload = SimpleUploadedFile("01_linear_regression.zip", file_content, content_type="application/zip")
    res_up = client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res_up.status_code == 201
    model_id = res_up.data["model_id"]
    model_version_id = res_up.data["model_version_id"]

    res_key = client.post("/api/keys/", {"model_id": model_id, "name": "pytorch-key"}, format="json")
    assert res_key.status_code == 201
    api_key = res_key.data["key"]

    dep = Deployment.objects.create(
        model_version_id=model_version_id,
        status=Deployment.Status.RUNNING,
        internal_url="http://runner:8001",
    )

    client.credentials(
        HTTP_AUTHORIZATION=client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key,
    )
    payload = {"instances": [{"f1": 0.5, "f2": 1.5}]}
    pred_res = client.post(f"/api/predict/{model_id}/", payload, format="json")
    assert pred_res.status_code == 200
    assert pred_res.data["predictions"] == [2.0]


def test_negative_artifact_malformed_yaml(uploader_client):
    """3D: Malformed YAML manifest is rejected with 400 Bad Request."""
    client, _ = uploader_client
    data = make_zip({"model.yaml": "invalid: [yaml: unclosed"})
    upload = SimpleUploadedFile("bad.zip", data, content_type="application/zip")
    res = client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 400


def test_negative_artifact_missing_declared_files(uploader_client):
    """3D: Manifest declaring files not present in zip is rejected with 400."""
    client, _ = uploader_client
    manifest = """
name: missing_files_model
framework: sklearn
python_version: "3.12"
requirements: requirements.txt
model_artifact: non_existent.pkl
task_type: regression
""".strip()

    # Zip contains model.yaml and requirements.txt, but non_existent.pkl is missing
    data = make_zip({
        "model.yaml": manifest,
        "requirements.txt": "scikit-learn==1.8.0\n",
    })
    upload = SimpleUploadedFile("missing.zip", data, content_type="application/zip")
    res = client.post("/api/models/upload/", {"file": upload}, format="multipart")
    assert res.status_code == 400
    assert "artifact" in str(res.data).lower() or "not found" in str(res.data).lower()
