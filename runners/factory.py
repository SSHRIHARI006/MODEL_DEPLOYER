from __future__ import annotations

from django.conf import settings

from .base import BaseRunner
from .pytorch import PyTorchRunner
from .sklearn import SklearnRunner


class RunnerFactory:
    @staticmethod
    def get_runner(*, framework: str) -> BaseRunner:
        timeout = int(getattr(settings, "INFERENCE_TIMEOUT_SECONDS", 15))

        if framework == "sklearn":
            base_url = getattr(settings, "RUNNER_SKLEARN_URL", "http://localhost:8002")
            return SklearnRunner(base_url=base_url, timeout_seconds=timeout)

        if framework == "pytorch":
            base_url = getattr(settings, "RUNNER_PYTORCH_URL", "http://localhost:8002")
            return PyTorchRunner(base_url=base_url, timeout_seconds=timeout)

        raise ValueError(f"Unsupported framework: {framework}")
