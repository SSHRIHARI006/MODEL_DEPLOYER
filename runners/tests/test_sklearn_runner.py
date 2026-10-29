from runners.auth import DEFAULT_AUTH_HEADER
from runners.sklearn import SklearnRunner

TOKEN = "unit-test-runner-token"
AUTH_HEADERS = {DEFAULT_AUTH_HEADER: TOKEN}


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.content = b"{}"

    def json(self):
        return self._json_data


def test_sklearn_runner_predict_sends_the_runner_credential(monkeypatch):
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append((url, headers))
        assert url.endswith("/predict")
        return DummyResponse(status_code=200, json_data={"predictions": [1]})

    monkeypatch.setattr("runners.sklearn.requests.post", fake_post)

    runner = SklearnRunner(
        base_url="http://runner",
        init_timeout_seconds=300,
        predict_timeout_seconds=5,
        healthcheck_timeout_seconds=30,
        command_timeout_seconds=60,
        auth_token=TOKEN,
    )
    result = runner.predict({"instances": [{"x": 1}]})

    assert result.status_code == 200
    assert result.data["predictions"] == [1]
    assert calls == [("http://runner/predict", AUTH_HEADERS)]


def test_sklearn_runner_healthcheck(monkeypatch):
    def fake_get(url, timeout, headers=None):
        assert url.endswith("/health")
        assert headers == AUTH_HEADERS
        return DummyResponse(status_code=200, json_data={"status": "ok"})

    monkeypatch.setattr("runners.sklearn.requests.get", fake_get)

    runner = SklearnRunner(
        base_url="http://runner",
        init_timeout_seconds=300,
        predict_timeout_seconds=15,
        healthcheck_timeout_seconds=5,
        command_timeout_seconds=60,
        auth_token=TOKEN,
    )
    result = runner.healthcheck()

    assert result.status_code == 200
    assert result.data["status"] == "ok"


def test_sklearn_runner_authenticates_init_model_and_teardown(monkeypatch):
    seen = []

    def fake_post(url, json, timeout, headers=None):
        seen.append((url, headers))
        return DummyResponse(status_code=200, json_data={})

    monkeypatch.setattr("runners.sklearn.requests.post", fake_post)

    runner = SklearnRunner(
        base_url="http://runner",
        init_timeout_seconds=300,
        predict_timeout_seconds=15,
        healthcheck_timeout_seconds=30,
        command_timeout_seconds=60,
        auth_token=TOKEN,
    )
    runner.init_environment({"model_id": "m1", "manifest_path": "/models/m1/model.yaml"})
    runner.teardown({"model_id": "m1"})

    assert seen == [
        ("http://runner/init-model", AUTH_HEADERS),
        ("http://runner/teardown", AUTH_HEADERS),
    ]


def test_sklearn_runner_honours_a_custom_auth_header(monkeypatch):
    seen = []

    def fake_post(url, json, timeout, headers=None):
        seen.append(headers)
        return DummyResponse(status_code=200, json_data={})

    monkeypatch.setattr("runners.sklearn.requests.post", fake_post)

    runner = SklearnRunner(
        base_url="http://runner",
        init_timeout_seconds=300,
        predict_timeout_seconds=15,
        healthcheck_timeout_seconds=30,
        command_timeout_seconds=60,
        auth_token=TOKEN,
        auth_header="X-Custom-Runner",
    )
    runner.predict({"instances": []})

    assert seen == [{"X-Custom-Runner": TOKEN}]


def test_sklearn_runner_sends_no_credential_when_unconfigured(monkeypatch):
    seen = []

    def fake_post(url, json, timeout, headers=None):
        seen.append(headers)
        return DummyResponse(status_code=200, json_data={})

    monkeypatch.setattr("runners.sklearn.requests.post", fake_post)

    runner = SklearnRunner(
        base_url="http://runner",
        init_timeout_seconds=300,
        predict_timeout_seconds=15,
        healthcheck_timeout_seconds=30,
        command_timeout_seconds=60,
    )
    runner.predict({"instances": []})

    # No token configured means no header is sent; the runner then rejects the
    # call, so a misconfigured control plane fails closed.
    assert seen == [{}]
