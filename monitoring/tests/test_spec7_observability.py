from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from deployments.models import Deployment
from monitoring.views import calculate_percentile, _compute_metrics
from prediction_gateway.models import PredictionLog

pytestmark = pytest.mark.django_db


def test_calculate_percentile_known_datasets():
    """OBS-01: Verify percentile calculation matches linear interpolation standard."""
    # Single element
    assert calculate_percentile([42.0], 0.95) == 42.0
    assert calculate_percentile([], 0.95) == 0.0

    # 5 evenly spaced values: [10, 20, 30, 40, 50]
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    # p50 is middle value: 30.0
    assert calculate_percentile(vals, 0.50) == 30.0
    # p95: k = 4 * 0.95 = 3.8 -> 40 + 0.8 * 10 = 48.0
    assert round(calculate_percentile(vals, 0.95), 2) == 48.0


def test_compute_metrics_separates_cache_hits_from_compute_latency(user, model_obj):
    """OBS-01: Cache hits must not pollute compute latency aggregates."""
    # Create 3 logs: 2 compute calls (100ms, 200ms) and 1 cache hit (gateway=5ms, compute=None)
    PredictionLog.objects.create(
        user=user,
        model=model_obj,
        input_data={"x": 1},
        status="SUCCESS",
        latency_ms=105.0,
        gateway_latency_ms=105.0,
        runner_compute_ms=100.0,
        cache_hit=False,
    )
    PredictionLog.objects.create(
        user=user,
        model=model_obj,
        input_data={"x": 2},
        status="SUCCESS",
        latency_ms=210.0,
        gateway_latency_ms=210.0,
        runner_compute_ms=200.0,
        cache_hit=False,
    )
    PredictionLog.objects.create(
        user=user,
        model=model_obj,
        input_data={"x": 1},
        status="SUCCESS",
        latency_ms=5.0,
        gateway_latency_ms=5.0,
        runner_compute_ms=None,
        cache_hit=True,
    )

    qs = PredictionLog.objects.filter(user=user)
    metrics = _compute_metrics(qs)

    assert metrics["total_requests"] == 3
    assert metrics["cache_hits"] == 1
    assert metrics["cache_hit_ratio"] == round(1 / 3, 4)
    # Average compute latency must be exactly mean(100, 200) = 150.0 (cache hit excluded!)
    assert metrics["avg_compute_latency_ms"] == 150.0


def test_staff_global_metrics_access_control(auth_client, user):
    """OBS-02: Non-staff users get 403; staff get 200 with global metrics."""
    # Non-staff caller -> 403
    res = auth_client.get("/api/metrics/global/")
    assert res.status_code == 403

    # Promote user to staff -> 200
    user.is_staff = True
    user.save()

    res_staff = auth_client.get("/api/metrics/global/")
    assert res_staff.status_code == 200
    assert "total_models" in res_staff.data
    assert "deployments" in res_staff.data
    assert "global_telemetry" in res_staff.data


def test_model_metrics_diagnostics_and_isolation(auth_client, user, user2, model_obj, model_version):
    """OBS-02: Model owners receive detailed deployment diagnostics; cross-owner gets 404."""
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        build_attempt=2,
        last_error_code="NONE",
        celery_task_id="task-xyz-123",
        build_logs="Build completed successfully",
    )

    # Owner GET model metrics -> 200 with full diagnostics
    res_owner = auth_client.get(f"/api/metrics/models/{model_obj.id}/")
    assert res_owner.status_code == 200
    data = res_owner.data
    assert data["latest_deployment_status"] == "RUNNING"
    assert data["latest_deployment_id"] == str(dep.id)
    assert data["latest_deployment_attempt"] == 2
    assert data["latest_deployment_task_id"] == "task-xyz-123"

    # Other user GET model metrics -> 404
    client_b = APIClient()
    login_b = client_b.post("/api/auth/login/", {"email": user2.email, "password": "TestPass123!"}, format="json")
    client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {login_b.data['access']}")
    res_b = client_b.get(f"/api/metrics/models/{model_obj.id}/")
    assert res_b.status_code == 404


def test_readiness_probe_endpoint(api_client, monkeypatch):
    """OBS-03: /api/metrics/ready/ checks dependencies and returns status."""
    # Mock runner health check to succeed
    class FakeResponse:
        status_code = 200

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())

    res = api_client.get("/api/metrics/ready/")
    assert res.status_code == 200
    assert res.data["status"] == "ready"
    assert res.data["database"] == "up"
    assert res.data["redis"] == "up"
    assert res.data["runner"] == "up"
