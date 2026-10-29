from __future__ import annotations

import json
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_malformed_json_returns_400(auth_client):
    """3B: Submitting invalid/malformed JSON returns 400 Bad Request with safe error."""
    res = auth_client.post(
        "/api/keys/universal/",
        data="{malformed: json",
        content_type="application/json",
    )
    assert res.status_code == 400
    # Must not leak traceback
    assert "Traceback" not in str(res.content)


def test_invalid_uuid_returns_404(auth_client):
    """3B: Supplying non-UUID values to UUID URL path converters returns 404."""
    bad_routes = [
        "/api/deployments/not-a-valid-uuid/",
        "/api/deployments/12345/stop/",
        "/api/keys/not-a-valid-uuid/deactivate/",
        "/api/keys/universal/not-a-valid-uuid/",
    ]
    for route in bad_routes:
        res = auth_client.get(route) if "stop" not in route and "deactivate" not in route else auth_client.post(route)
        assert res.status_code == 404, f"Expected 404 for {route}, got {res.status_code}"


def test_register_validation_contracts(api_client):
    """3B: Registration requires valid fields and rejects duplicates/short passwords."""
    # Missing fields
    res = api_client.post("/api/auth/register/", {}, format="json")
    assert res.status_code == 400

    # Weak/empty password
    res = api_client.post(
        "/api/auth/register/",
        {"email": "valid@example.com", "username": "validuser", "password": ""},
        format="json",
    )
    assert res.status_code == 400


def test_login_validation_contracts(api_client, user):
    """3B: Login requires email and password; wrong password returns 401."""
    # Empty payload
    res = api_client.post("/api/auth/login/", {}, format="json")
    assert res.status_code == 400

    # Wrong password
    res = api_client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "WrongPassword123!"},
        format="json",
    )
    assert res.status_code == 401


def test_model_api_key_creation_validation(auth_client):
    """3B: Model API key creation requires model_id and name."""
    res = auth_client.post("/api/keys/", {}, format="json")
    assert res.status_code == 400
    assert "model_id" in res.data or "name" in res.data


def test_wallet_deposit_validation(auth_client, user, settings):
    """3B: Wallet deposit validates permissions and amount (positive, numeric)."""
    # Without demo deposits enabled -> 403
    settings.BILLING_DEMO_DEPOSITS = False
    res = auth_client.post("/api/wallet/deposit/", {"amount": 10}, format="json")
    assert res.status_code == 403

    # With demo deposits enabled and staff user -> validates amount
    settings.BILLING_DEMO_DEPOSITS = True
    user.is_staff = True
    user.save()

    # Negative amount -> 400
    res_neg = auth_client.post("/api/wallet/deposit/", {"amount": -10}, format="json")
    assert res_neg.status_code == 400

    # Zero amount -> 400
    res_zero = auth_client.post("/api/wallet/deposit/", {"amount": 0}, format="json")
    assert res_zero.status_code == 400

    # Non-numeric -> 400
    res_str = auth_client.post("/api/wallet/deposit/", {"amount": "not-a-number"}, format="json")
    assert res_str.status_code == 400


def test_deployment_create_validation(auth_client):
    """3B: Deployment creation requires model_version_id."""
    res = auth_client.post("/api/deployments/", {}, format="json")
    assert res.status_code == 400
    assert "model_version_id" in res.data or "error" in res.data
