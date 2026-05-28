from runners.sklearn import SklearnRunner


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.content = b"{}"

    def json(self):
        return self._json_data


def test_sklearn_runner_predict(monkeypatch):
    def fake_post(url, json, timeout):
        assert url.endswith("/predict")
        return DummyResponse(status_code=200, json_data={"predictions": [1]})

    monkeypatch.setattr("runners.sklearn.requests.post", fake_post)

    runner = SklearnRunner(base_url="http://runner", timeout_seconds=5)
    result = runner.predict({"instances": [{"x": 1}]})

    assert result.status_code == 200
    assert result.data["predictions"] == [1]


def test_sklearn_runner_healthcheck(monkeypatch):
    def fake_get(url, timeout):
        assert url.endswith("/health")
        return DummyResponse(status_code=200, json_data={"status": "ok"})

    monkeypatch.setattr("runners.sklearn.requests.get", fake_get)

    runner = SklearnRunner(base_url="http://runner", timeout_seconds=5)
    result = runner.healthcheck()

    assert result.status_code == 200
    assert result.data["status"] == "ok"
