from __future__ import annotations

from django.conf import settings

from .auth import DEFAULT_AUTH_HEADER
from .base import BaseRunner
from .pytorch import PyTorchRunner
from .sklearn import SklearnRunner


class RunnerFactory:
    @staticmethod
    def get_runner(*, framework: str) -> BaseRunner:
        auth_token = getattr(settings, "RUNNER_AUTH_TOKEN", "") or ""
        auth_header = (
            getattr(settings, "RUNNER_AUTH_HEADER", "") or DEFAULT_AUTH_HEADER
        )

        init_timeout = int(getattr(settings, "RUNNER_INIT_TIMEOUT_SECONDS", 300))
        predict_timeout = int(getattr(settings, "RUNNER_PREDICT_TIMEOUT_SECONDS", 15))
        healthcheck_timeout = int(getattr(settings, "RUNNER_HEALTHCHECK_TIMEOUT_SECONDS", 30))
        command_timeout = int(getattr(settings, "RUNNER_COMMAND_TIMEOUT_SECONDS", 60))

        base_url = getattr(settings, "RUNNER_BASE_URL", "http://localhost:8002")

        if framework == "sklearn":
            return SklearnRunner(
                base_url=base_url,
                init_timeout_seconds=init_timeout,
                predict_timeout_seconds=predict_timeout,
                healthcheck_timeout_seconds=healthcheck_timeout,
                command_timeout_seconds=command_timeout,
                auth_token=auth_token,
                auth_header=auth_header,
            )

        if framework == "pytorch":
            return PyTorchRunner(
                base_url=base_url,
                init_timeout_seconds=init_timeout,
                predict_timeout_seconds=predict_timeout,
                healthcheck_timeout_seconds=healthcheck_timeout,
                command_timeout_seconds=command_timeout,
                auth_token=auth_token,
                auth_header=auth_header,
            )

        raise ValueError(f"Unsupported framework: {framework}")
