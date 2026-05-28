from __future__ import annotations

import requests

from .base import BaseRunner, RunnerResult


class SklearnRunner(BaseRunner):
    def init_environment(self, payload: dict) -> RunnerResult:
        url = f"{self.base_url}/init-model"
        response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        return RunnerResult(status_code=response.status_code, data=_safe_json(response))

    def predict(self, payload: dict) -> RunnerResult:
        url = f"{self.base_url}/predict"
        response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        return RunnerResult(status_code=response.status_code, data=_safe_json(response))

    def healthcheck(self) -> RunnerResult:
        url = f"{self.base_url}/health"
        response = requests.get(url, timeout=self.timeout_seconds)
        return RunnerResult(status_code=response.status_code, data=_safe_json(response))

    def teardown(self, payload: dict) -> RunnerResult:
        url = f"{self.base_url}/teardown"
        response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        return RunnerResult(status_code=response.status_code, data=_safe_json(response))


def _safe_json(response: requests.Response) -> dict:
    try:
        return response.json() if response.content else {}
    except ValueError:
        return {"raw": response.text}
