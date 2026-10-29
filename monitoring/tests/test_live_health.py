from __future__ import annotations

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_live_health_endpoint_public_and_healthy():
    """REL-10: GET /api/metrics/live/ returns 200 without authentication or DB queries."""
    client = APIClient()
    res = client.get("/api/metrics/live/")
    assert res.status_code == 200
    assert res.data == {"status": "alive"}
