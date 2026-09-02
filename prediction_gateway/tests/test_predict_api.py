import pytest
import requests
from deployments.models import Deployment
from prediction_gateway.models import PredictionLog
from runners.base import RunnerResult

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
    res = api_client.post(
        f"/api/predict/{model_obj.id}/", {"input": [1]}, format="json"
    )
    assert res.status_code == 401


def test_predict_invalid_api_key(auth_client, model_obj):
    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY="bad-key",
    )
    res = auth_client.post(
        f"/api/predict/{model_obj.id}/", {"input": [1]}, format="json"
    )
    assert res.status_code == 403


def test_predict_returns_503_when_no_running_deployment(
    auth_client, model_obj, model_version, api_key
):
    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1}]},
        format="json",
    )

    assert res.status_code == 503


def test_predict_success_creates_success_log(
    auth_client, model_obj, model_version, api_key, monkeypatch
):
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    class DummyRunner:
        def predict(self, payload):
            assert "instances" in payload
            return RunnerResult(status_code=200, data={"predictions": [1]})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: DummyRunner(),
    )

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1}]},
        format="json",
    )

    assert res.status_code == 200
    assert res.data["predictions"] == [1]
    assert PredictionLog.objects.filter(
        model=model_obj, status="SUCCESS", deployment=dep
    ).exists()


def test_predict_connection_error_maps_502(
    auth_client, model_obj, model_version, api_key, monkeypatch
):
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    class DummyRunner:
        def predict(self, payload):
            raise requests.ConnectionError("refused")

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: DummyRunner(),
    )

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1}]},
        format="json",
    )

    assert res.status_code == 502
    assert PredictionLog.objects.filter(model=model_obj, status="ERROR").exists()


def test_predict_timeout_maps_504(
    auth_client, model_obj, model_version, api_key, monkeypatch
):
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    class DummyRunner:
        def predict(self, payload):
            raise requests.Timeout("timed out")

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: DummyRunner(),
    )

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1}]},
        format="json",
    )

    assert res.status_code == 504


def test_predict_uses_cache_for_repeated_input(
    auth_client, model_obj, model_version, api_key, monkeypatch
):
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    class DummyRunner:
        calls = 0

        def predict(self, payload):
            self.calls += 1
            return RunnerResult(status_code=200, data={"predictions": [2]})

    runner = DummyRunner()
    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: runner,
    )

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    payload = {"instances": [{"x": 1}]}
    first = auth_client.post(f"/api/predict/{model_obj.id}/", payload, format="json")
    second = auth_client.post(f"/api/predict/{model_obj.id}/", payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data == first.data
    assert runner.calls == 1
    assert PredictionLog.objects.filter(model=model_obj, status="SUCCESS").count() == 2


def test_prediction_cache_key_changes_with_model_version(model_obj, model_version):
    from prediction_gateway.views import prediction_cache_key

    other_version = model_obj.versions.create(
        version="v2", artifact_path="/tmp/other-artifacts", status="READY"
    )

    first_key = prediction_cache_key(model_obj.id, model_version.id, [{"x": 1}])
    second_key = prediction_cache_key(model_obj.id, other_version.id, [{"x": 1}])

    assert first_key != second_key


def test_predict_client_error_passthrough_400(
    auth_client, model_obj, model_version, api_key, monkeypatch
):
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )

    class DummyRunner:
        def predict(self, payload):
            return RunnerResult(status_code=400, data={"error": "bad input"})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: DummyRunner(),
    )

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key.key,
    )
    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1}]},
        format="json",
    )

    assert res.status_code == 400
    assert res.data["error"] == "bad input"
