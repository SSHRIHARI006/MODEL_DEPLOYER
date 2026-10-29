import pytest

from django.test import override_settings

from runners.factory import RunnerFactory
from runners.pytorch import PyTorchRunner
from runners.sklearn import SklearnRunner


def test_factory_returns_sklearn_runner():
    runner = RunnerFactory.get_runner(framework="sklearn")
    assert isinstance(runner, SklearnRunner)


def test_factory_returns_pytorch_runner():
    runner = RunnerFactory.get_runner(framework="pytorch")
    assert isinstance(runner, PyTorchRunner)


def test_factory_unsupported_framework():
    with pytest.raises(ValueError):
        RunnerFactory.get_runner(framework="unknown")


def test_factory_uses_override_settings():
    with override_settings(
        RUNNER_BASE_URL="http://runner:9000",
        RUNNER_SKLEARN_URL="http://runner:9000",
    ):
        runner = RunnerFactory.get_runner(framework="sklearn")
        assert runner.base_url == "http://runner:9000"


def test_factory_uses_pytorch_override_settings():
    with override_settings(
        RUNNER_BASE_URL="http://runner:9001",
        RUNNER_PYTORCH_URL="http://runner:9001",
    ):
        runner = RunnerFactory.get_runner(framework="pytorch")
        assert runner.base_url == "http://runner:9001"


def test_factory_passes_the_configured_runner_credential():
    with override_settings(
        RUNNER_AUTH_TOKEN="factory-token", RUNNER_AUTH_HEADER="X-Runner-Token"
    ):
        sklearn_runner = RunnerFactory.get_runner(framework="sklearn")
        pytorch_runner = RunnerFactory.get_runner(framework="pytorch")

    assert sklearn_runner.auth_token == "factory-token"
    assert pytorch_runner.auth_token == "factory-token"
    assert sklearn_runner._request_headers() == {"X-Runner-Token": "factory-token"}


def test_factory_honours_a_custom_runner_auth_header():
    with override_settings(RUNNER_AUTH_TOKEN="factory-token", RUNNER_AUTH_HEADER="X-Alt"):
        runner = RunnerFactory.get_runner(framework="sklearn")

    assert runner._request_headers() == {"X-Alt": "factory-token"}


def test_factory_without_a_configured_token_sends_no_credential():
    with override_settings(RUNNER_AUTH_TOKEN=""):
        runner = RunnerFactory.get_runner(framework="sklearn")

    assert runner._request_headers() == {}


def test_factory_uses_separate_runner_timeouts():
    with override_settings(
        RUNNER_BASE_URL="http://runner:9002",
        RUNNER_INIT_TIMEOUT_SECONDS="10",
        RUNNER_PREDICT_TIMEOUT_SECONDS="5",
        RUNNER_HEALTHCHECK_TIMEOUT_SECONDS="7",
        RUNNER_COMMAND_TIMEOUT_SECONDS="3",
    ):
        runner = RunnerFactory.get_runner(framework="sklearn")
        assert runner.init_timeout_seconds == 10
        assert runner.predict_timeout_seconds == 5
        assert runner.healthcheck_timeout_seconds == 7
        assert runner.command_timeout_seconds == 3


def test_factory_uses_default_runner_base_url_when_only_legacy_urls_set():
    with override_settings(
        RUNNER_BASE_URL="http://default-worker:8002",
        RUNNER_SKLEARN_URL="http://legacy-sklearn:8002",
        RUNNER_PYTORCH_URL="http://legacy-pytorch:8002",
    ):
        sklearn_runner = RunnerFactory.get_runner(framework="sklearn")
        pytorch_runner = RunnerFactory.get_runner(framework="pytorch")
        assert sklearn_runner.base_url == "http://default-worker:8002"
        assert pytorch_runner.base_url == "http://default-worker:8002"

