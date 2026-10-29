from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from runners.auth import DEFAULT_AUTH_HEADER
from runners.base import RunnerResult
from runners.pytorch import PyTorchRunner

pytestmark = pytest.mark.django_db

TOKEN = "unit-test-runner-token"
AUTH_HEADERS = {DEFAULT_AUTH_HEADER: TOKEN}


@pytest.fixture
def runner():
    return PyTorchRunner(
        base_url="http://test-pytorch:8000",
        init_timeout_seconds=300,
        predict_timeout_seconds=5,
        healthcheck_timeout_seconds=30,
        command_timeout_seconds=60,
        auth_token=TOKEN,
    )


class TestPyTorchRunnerInit:
    def test_base_url_trailing_slash_stripped(self):
        r = PyTorchRunner(
            base_url="http://test:8000/",
            init_timeout_seconds=300,
            predict_timeout_seconds=15,
            healthcheck_timeout_seconds=30,
            command_timeout_seconds=60,
        )
        assert r.base_url == "http://test:8000"

    def test_timeouts_stored(self, runner):
        assert runner.init_timeout_seconds == 300
        assert runner.predict_timeout_seconds == 5
        assert runner.healthcheck_timeout_seconds == 30
        assert runner.command_timeout_seconds == 60

    def test_auth_token_stored(self, runner):
        assert runner.auth_token == TOKEN
        assert runner.auth_header == DEFAULT_AUTH_HEADER


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
            timeout=300,
            headers=AUTH_HEADERS,
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
        assert mock_post.call_args.kwargs["headers"] == AUTH_HEADERS

    @patch("runners.pytorch.requests.get")
    def test_healthcheck(self, mock_get, runner):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "ok"}'
        mock_resp.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_resp

        result = runner.healthcheck()
        assert result.status_code == 200
        assert mock_get.call_args.kwargs["headers"] == AUTH_HEADERS

    @patch("runners.pytorch.requests.post")
    def test_teardown(self, mock_post, runner):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "deleted"}'
        mock_resp.json.return_value = {"status": "deleted"}
        mock_post.return_value = mock_resp

        result = runner.teardown({"model_id": "abc"})
        assert result.status_code == 200
        assert mock_post.call_args.kwargs["headers"] == AUTH_HEADERS

    @patch("runners.pytorch.requests.post")
    def test_unconfigured_runner_sends_no_credential(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.content = b'{"detail": "missing or invalid runner credentials"}'
        mock_resp.json.return_value = {"detail": "missing or invalid runner credentials"}
        mock_post.return_value = mock_resp

        runner = PyTorchRunner(
            base_url="http://test-pytorch:8000",
            init_timeout_seconds=300,
            predict_timeout_seconds=15,
            healthcheck_timeout_seconds=30,
            command_timeout_seconds=60,
        )
        result = runner.predict({"model_id": "abc", "instances": []})

        assert mock_post.call_args.kwargs["headers"] == {}
        assert result.status_code == 401
