import pytest
from django.utils import timezone

from prediction_gateway.models import PredictionLog

pytestmark = pytest.mark.django_db


def _create_log(*, user, model, status, latency):
    return PredictionLog.objects.create(
        uid=f"dashboard-log-{timezone.now().timestamp()}-{status}",
        user=user,
        model=model,
        deployment=None,
        input_data={"input": [1]},
        output_data={"prediction": [1]} if status == "SUCCESS" else {},
        latency_ms=latency,
        status=status,
        error_message="err" if status == "ERROR" else None,
    )


def test_dashboard_summary_requires_auth(api_client):
    res = api_client.get("/api/metrics/dashboard/summary/")
    assert res.status_code == 401


def test_dashboard_summary_returns_expected_fields(auth_client, user, model_obj, api_key):
    _create_log(user=user, model=model_obj, status="SUCCESS", latency=100)

    res = auth_client.get("/api/metrics/dashboard/summary/")
    assert res.status_code == 200
    assert "metrics" in res.data
    assert "model_count" in res.data
    assert "active_api_keys" in res.data
    assert "recent_requests_24h" in res.data
    assert res.data["model_count"] >= 1
    assert res.data["active_api_keys"] >= 1


def test_dashboard_recent_predictions_scopes_to_user(auth_client, user, model_obj, user2, model_obj_user2):
    _create_log(user=user, model=model_obj, status="SUCCESS", latency=100)
    _create_log(user=user, model=model_obj, status="ERROR", latency=150)
    _create_log(user=user2, model=model_obj_user2, status="SUCCESS", latency=999)

    res = auth_client.get("/api/metrics/dashboard/recent-predictions/?limit=2")
    assert res.status_code == 200
    assert len(res.data) == 2
    assert all(item["model_id"] == model_obj.id for item in res.data)


def test_dashboard_models_returns_per_model_cards(auth_client, user, model_obj):
    _create_log(user=user, model=model_obj, status="SUCCESS", latency=100)
    _create_log(user=user, model=model_obj, status="ERROR", latency=200)

    res = auth_client.get("/api/metrics/dashboard/models/")
    assert res.status_code == 200
    assert len(res.data) >= 1

    item = next(row for row in res.data if row["model_id"] == model_obj.id)
    assert item["total_requests"] == 2
    assert item["success_count"] == 1
    assert item["error_count"] == 1
