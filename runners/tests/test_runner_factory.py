import pytest

from django.test import override_settings

from runners.factory import RunnerFactory
from runners.sklearn import SklearnRunner


def test_factory_returns_sklearn_runner():
    runner = RunnerFactory.get_runner(framework="sklearn")
    assert isinstance(runner, SklearnRunner)


def test_factory_unsupported_framework():
    with pytest.raises(ValueError):
        RunnerFactory.get_runner(framework="unknown")


def test_factory_uses_override_settings():
    with override_settings(RUNNER_SKLEARN_URL="http://runner:9000"):
        runner = RunnerFactory.get_runner(framework="sklearn")
        assert runner.base_url == "http://runner:9000"
