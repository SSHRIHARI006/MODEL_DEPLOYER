from __future__ import annotations

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


PROTECTED_GET_ROUTES = [
    "/api/deployments/",
    "/api/keys/",
    "/api/keys/universal/",
    "/api/wallet/",
    "/api/dashboard/summary/",
    "/api/metrics/overview/",
    "/api/metrics/dashboard/summary/",
    "/api/metrics/dashboard/recent-predictions/",
    "/api/metrics/dashboard/models/",
]

PUBLIC_GET_ROUTES = [
    "/api/models/explore/",
    "/api/metrics/live/",
    "/api/metrics/ready/",
    "/api/metrics/health/",
]


@pytest.mark.parametrize("route", PROTECTED_GET_ROUTES)
def test_protected_routes_reject_anonymous_callers(route):
    """3B: Protected routes must reject anonymous callers with 401."""
    client = APIClient()
    res = client.get(route)
    assert res.status_code == 401, f"Expected 401 for {route}, got {res.status_code}"


@pytest.mark.parametrize("route", PROTECTED_GET_ROUTES)
def test_protected_routes_reject_invalid_token(route):
    """3B: Protected routes must reject invalid or malformed tokens with 401."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid-garbage-token")
    res = client.get(route)
    assert res.status_code == 401, f"Expected 401 for {route}, got {res.status_code}"


@pytest.mark.parametrize("route", PROTECTED_GET_ROUTES)
def test_protected_routes_accept_authenticated_callers(auth_client, route):
    """3B: Protected routes return 200 for authenticated callers."""
    res = auth_client.get(route)
    assert res.status_code == 200, f"Expected 200 for {route}, got {res.status_code}: {res.data}"


@pytest.mark.parametrize("route", PUBLIC_GET_ROUTES)
def test_public_routes_serve_anonymous_callers(route):
    """3B: Public routes serve anonymous callers without requiring authentication."""
    client = APIClient()
    res = client.get(route)
    assert res.status_code in (200, 503), f"Expected 200/503 for {route}, got {res.status_code}"
    assert res.status_code != 401


def test_method_not_allowed_on_disallowed_methods(auth_client):
    """3B: Disallowed HTTP methods return 405 Method Not Allowed."""
    # PUT on explore is not allowed
    res_explore = auth_client.put("/api/models/explore/", {})
    assert res_explore.status_code == 405

    # DELETE on explore is not allowed
    res_del_explore = auth_client.delete("/api/models/explore/")
    assert res_del_explore.status_code == 405

    # PUT on deployments collection is not allowed
    res_dep = auth_client.put("/api/deployments/", {})
    assert res_dep.status_code == 405

    # PATCH on deployments collection is not allowed
    res_patch_dep = auth_client.patch("/api/deployments/", {})
    assert res_patch_dep.status_code == 405

    # PUT on live health is not allowed
    client = APIClient()
    res_live = client.put("/api/metrics/live/", {})
    assert res_live.status_code == 405


def test_unknown_routes_return_404():
    """3B: Unknown routes return 404 cleanly."""
    client = APIClient()
    res = client.get("/api/nonexistent/endpoint/")
    assert res.status_code == 404
