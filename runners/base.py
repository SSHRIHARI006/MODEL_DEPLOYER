from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RunnerResult:
    status_code: int
    data: dict


class BaseRunner(ABC):
    def __init__(self, base_url: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

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
    def teardown(self, payload: dict) -> RunnerResult:
        raise NotImplementedError
