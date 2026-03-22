import pytest
from prediction_gateway.models import PredictionLog

pytestmark = pytest.mark.django_db


def test_predict_requires_auth(api_client, model_obj):
    res = api_client.post(f"/api/predict/{model_obj.id}/", {"input": [1]}, format="json")
    assert res.status_code == 401


def test_predict_invalid_api_key(auth_client, model_obj):
    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY="bad-key",
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [1]}, format="json")
    assert res.status_code == 403


def test_predict_success_creates_success_log(auth_client, model_obj, model_version, api_key, monkeypatch):
    def fake_run_inference(model_path, data):
        return [8.0]

    monkeypatch.setattr("prediction_gateway.views.run_inference", fake_run_inference)

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 200
    assert "prediction" in res.data
    assert PredictionLog.objects.filter(model=model_obj, status="SUCCESS").exists()


def test_predict_error_creates_error_log(auth_client, model_obj, model_version, api_key, monkeypatch):
    def fake_run_inference(model_path, data):
        raise Exception("boom")  # generic exception -> 500

    monkeypatch.setattr("prediction_gateway.views.run_inference", fake_run_inference)

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 500

def test_predict_client_error_returns_400(auth_client, model_obj, model_version, api_key, monkeypatch):
    from prediction_gateway.views import InferenceClientError

    def fake_run_inference(model_path, data):
        raise InferenceClientError("bad input")

    monkeypatch.setattr("prediction_gateway.views.run_inference", fake_run_inference)

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 400    