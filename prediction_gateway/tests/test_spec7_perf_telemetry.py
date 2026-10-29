from __future__ import annotations

import concurrent.futures
import time
import pytest
from rest_framework.test import APIClient

from deployments.models import Deployment
from prediction_gateway.models import PredictionLog
from prediction_gateway.singleflight import SingleFlight
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db


def test_prediction_telemetry_fields_recorded(auth_client, model_obj, model_version, monkeypatch):
    """OBS-01: Verify cache_hit, gateway_latency_ms, and runner_compute_ms are populated."""
    class FakeRunner:
        def predict(self, payload):
            time.sleep(0.01)  # 10ms compute
            return RunnerResult(status_code=200, data={"predictions": [99.0]})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: FakeRunner(),
    )

    Deployment.objects.create(
        model_version=model_version,
        status="RUNNING",
        internal_url="http://runner:8001",
    )

    res_key = auth_client.post("/api/keys/", {"model_id": model_obj.id, "name": "telemetry-key"}, format="json")
    api_key = res_key.data["key"]

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key,
    )

    payload = {"instances": [{"v": 1.0}]}

    # 1. First call: cache miss
    r1 = auth_client.post(f"/api/predict/{model_obj.id}/", payload, format="json")
    assert r1.status_code == 200

    log1 = PredictionLog.objects.filter(model=model_obj).order_by("-created_at").first()
    assert log1 is not None
    assert log1.cache_hit is False
    assert log1.gateway_latency_ms is not None and log1.gateway_latency_ms > 0
    assert log1.runner_compute_ms is not None and log1.runner_compute_ms > 0

    # 2. Second call: cache hit
    r2 = auth_client.post(f"/api/predict/{model_obj.id}/", payload, format="json")
    assert r2.status_code == 200

    log2 = PredictionLog.objects.filter(model=model_obj).order_by("-created_at").first()
    assert log2 is not None
    assert log2.id != log1.id
    assert log2.cache_hit is True
    assert log2.gateway_latency_ms is not None
    assert log2.runner_compute_ms is None  # Cache hit must have None compute latency


def test_single_flight_coordination():
    """PERF-02: Simultaneous identical executions share 1 underlying call."""
    sf = SingleFlight(lock_timeout_sec=2.0, poll_interval_sec=0.01)
    shared_cache: dict[str, Any] = {}
    underlying_calls = 0

    def compute():
        nonlocal underlying_calls
        underlying_calls += 1
        time.sleep(0.05)
        res = {"result": 42}
        shared_cache["key-1"] = res
        return res

    def get_cache(k: str):
        return shared_cache.get(k)

    def worker():
        res, was_cached = sf.execute("key-1", compute, get_cache)
        return res, was_cached

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker) for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # All 5 workers received the correct result
    for res, _ in results:
        assert res == {"result": 42}

    # Only 1 underlying execution occurred!
    assert underlying_calls == 1


def test_single_flight_failure_does_not_hang_waiters():
    """PERF-02: Leader failure releases lock and does not deadlock waiters."""
    sf = SingleFlight(lock_timeout_sec=0.5, poll_interval_sec=0.01)
    call_attempts = 0

    def failing_compute():
        nonlocal call_attempts
        call_attempts += 1
        time.sleep(0.02)
        raise RuntimeError("Inference boom")

    def get_cache(k: str):
        return None

    def worker():
        try:
            return sf.execute("fail-key", failing_compute, get_cache)
        except RuntimeError as e:
            return str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        r1 = f1.result(timeout=2.0)
        r2 = f2.result(timeout=2.0)

    assert "Inference boom" in str(r1)
    assert "Inference boom" in str(r2)
