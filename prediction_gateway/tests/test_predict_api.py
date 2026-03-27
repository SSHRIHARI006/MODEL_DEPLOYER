import pytest
import requests
from deployments.models import Deployment
from prediction_gateway.models import PredictionLog

pytestmark = pytest.mark.django_db


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.content = b"{}"

    def json(self):
        return self._json_data


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


def test_predict_returns_503_when_no_running_deployment(auth_client, model_obj, model_version, api_key):
    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 503


def test_predict_success_creates_success_log(auth_client, model_obj, model_version, api_key, monkeypatch):
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    def fake_post(url, json, timeout):
        assert url == "http://model_test:5000/predict"
        return DummyResponse(status_code=200, json_data={"prediction": [8.0]})

    monkeypatch.setattr("prediction_gateway.views.requests.post", fake_post)

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 200
    assert res.data["prediction"] == [8.0]
    assert PredictionLog.objects.filter(model=model_obj, status="SUCCESS", deployment=dep).exists()


def test_predict_connection_error_maps_502(auth_client, model_obj, model_version, api_key, monkeypatch):
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    def fake_post(url, json, timeout):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr("prediction_gateway.views.requests.post", fake_post)

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 502
    assert PredictionLog.objects.filter(model=model_obj, status="ERROR").exists()


def test_predict_timeout_maps_504(auth_client, model_obj, model_version, api_key, monkeypatch):
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    def fake_post(url, json, timeout):
        raise requests.Timeout("timed out")

    monkeypatch.setattr("prediction_gateway.views.requests.post", fake_post)

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 504


def test_predict_client_error_passthrough_400(auth_client, model_obj, model_version, api_key, monkeypatch):
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    def fake_post(url, json, timeout):
        return DummyResponse(status_code=400, json_data={"error": "bad input"})

    monkeypatch.setattr("prediction_gateway.views.requests.post", fake_post)

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(f"/api/predict/{model_obj.id}/", {"input": [4]}, format="json")

    assert res.status_code == 400
    assert res.data["error"] == "bad input"