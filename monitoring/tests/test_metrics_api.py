import pytest
from django.utils import timezone

from prediction_gateway.models import PredictionLog

pytestmark = pytest.mark.django_db


def _create_log(*, user, model, status, latency):
    return PredictionLog.objects.create(
        uid=f"log-{timezone.now().timestamp()}-{status}",
        user=user,
        model=model,
        deployment=None,
        input_data={"input": [1]},
        output_data={"prediction": [1]} if status == "SUCCESS" else {},
        latency_ms=latency,
        status=status,
        error_message="err" if status == "ERROR" else None,
    )


def test_metrics_overview_requires_auth(api_client):
    res = api_client.get("/api/metrics/overview/")
    assert res.status_code == 401


def test_metrics_overview_empty(auth_client):
    res = auth_client.get("/api/metrics/overview/")
    assert res.status_code == 200
    assert res.data["total_requests"] == 0
    assert res.data["success_count"] == 0
    assert res.data["error_count"] == 0
    assert res.data["success_rate"] == 0.0


def test_metrics_overview_aggregates(auth_client, user, model_obj):
    _create_log(user=user, model=model_obj, status="SUCCESS", latency=100)
    _create_log(user=user, model=model_obj, status="SUCCESS", latency=200)
    _create_log(user=user, model=model_obj, status="ERROR", latency=50)

    res = auth_client.get("/api/metrics/overview/")
    assert res.status_code == 200
    assert res.data["total_requests"] == 3
    assert res.data["success_count"] == 2
    assert res.data["error_count"] == 1
    assert res.data["success_rate"] == pytest.approx(66.67, abs=0.01)
    assert res.data["avg_latency_ms"] == pytest.approx(116.667, abs=0.01)
    assert res.data["p95_latency_ms"] == pytest.approx(100.0, abs=0.01)


def test_model_metrics_only_owner_data(auth_client, user, model_obj, user2, model_obj_user2):
    _create_log(user=user, model=model_obj, status="SUCCESS", latency=120)
    _create_log(user=user2, model=model_obj_user2, status="SUCCESS", latency=999)

    res = auth_client.get(f"/api/metrics/models/{model_obj.id}/")
    assert res.status_code == 200
    assert res.data["model_id"] == model_obj.id
    assert res.data["total_requests"] == 1


def test_model_metrics_for_other_user_model_forbidden(auth_client, model_obj_user2):
    res = auth_client.get(f"/api/metrics/models/{model_obj_user2.id}/")
    assert res.status_code == 404
