from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .auth import DEFAULT_AUTH_HEADER, auth_headers


@dataclass(frozen=True)
class RunnerResult:
    status_code: int
    data: dict


class BaseRunner(ABC):
    def __init__(
        self,
        base_url: str,
        init_timeout_seconds: int,
        predict_timeout_seconds: int,
        healthcheck_timeout_seconds: int,
        command_timeout_seconds: int,
        auth_token: str = "",
        auth_header: str = DEFAULT_AUTH_HEADER,
    ):
        self.base_url = base_url.rstrip("/")
        self.init_timeout_seconds = init_timeout_seconds
        self.predict_timeout_seconds = predict_timeout_seconds
        self.healthcheck_timeout_seconds = healthcheck_timeout_seconds
        self.command_timeout_seconds = command_timeout_seconds
        self.auth_token = auth_token or ""
        self.auth_header = auth_header or DEFAULT_AUTH_HEADER

    def _request_headers(self) -> dict[str, str]:
        """Credential header for internal runner routes (SEC-02)."""
        return auth_headers(self.auth_token, self.auth_header)

    @abstractmethod
    def init_environment(self, payload: dict) -> RunnerResult:
        raise NotImplementedError

    @abstractmethod
    def predict(self, payload: dict) -> RunnerResult:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> RunnerResult:
        raise NotImplementedError

    @abstractmethod
    def readiness(self) -> RunnerResult:
        raise NotImplementedError

    @abstractmethod
    def teardown(self, payload: dict) -> RunnerResult:
        raise NotImplementedError
