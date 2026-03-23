import pytest

pytestmark = pytest.mark.django_db


def test_health_endpoint_returns_ok_or_degraded(api_client):
    res = api_client.get("/api/metrics/health/")
    assert res.status_code in (200, 503)
    assert res.data["status"] in ("ok", "degraded")
    assert "database" in res.data
    assert "timestamp" in res.data
