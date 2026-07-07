from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from runners.base import RunnerResult
from runners.pytorch import PyTorchRunner

pytestmark = pytest.mark.django_db


@pytest.fixture
def runner():
    return PyTorchRunner(base_url="http://test-pytorch:8000", timeout_seconds=5)


class TestPyTorchRunnerInit:
    def test_base_url_trailing_slash_stripped(self):
        r = PyTorchRunner(base_url="http://test:8000/", timeout_seconds=5)
        assert r.base_url == "http://test:8000"

    def test_timeout_stored(self, runner):
        assert runner.timeout_seconds == 5


class TestPyTorchRunnerMethods:
    @patch("runners.pytorch.requests.post")
    def test_init_environment(self, mock_post, runner):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "ready"}'
        mock_resp.json.return_value = {"status": "ready"}
        mock_post.return_value = mock_resp

        result = runner.init_environment({"model_id": "abc", "manifest_path": "/m"})
        assert isinstance(result, RunnerResult)
        assert result.status_code == 200
        mock_post.assert_called_once_with(
            "http://test-pytorch:8000/init-model",
            json={"model_id": "abc", "manifest_path": "/m"},
            timeout=5,
        )

    @patch("runners.pytorch.requests.post")
    def test_predict(self, mock_post, runner):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"predictions": [1, 0]}'
        mock_resp.json.return_value = {"predictions": [1, 0]}
        mock_post.return_value = mock_resp

        result = runner.predict({"model_id": "abc", "instances": [{"x": 1}]})
        assert result.status_code == 200
        assert result.data["predictions"] == [1, 0]

    @patch("runners.pytorch.requests.get")
    def test_healthcheck(self, mock_get, runner):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "ok"}'
        mock_resp.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_resp

        result = runner.healthcheck()
        assert result.status_code == 200

    @patch("runners.pytorch.requests.post")
    def test_teardown(self, mock_post, runner):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "deleted"}'
        mock_resp.json.return_value = {"status": "deleted"}
        mock_post.return_value = mock_resp

        result = runner.teardown({"model_id": "abc"})
        assert result.status_code == 200
