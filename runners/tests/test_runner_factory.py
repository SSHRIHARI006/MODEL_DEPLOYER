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
    with override_settings(RUNNER_SKLEARN_URL="http://runner:9000"):
        runner = RunnerFactory.get_runner(framework="sklearn")
        assert runner.base_url == "http://runner:9000"


def test_factory_uses_pytorch_override_settings():
    with override_settings(RUNNER_PYTORCH_URL="http://runner:9001"):
        runner = RunnerFactory.get_runner(framework="pytorch")
        assert runner.base_url == "http://runner:9001"

