"""SEC-06: the anonymous profile endpoint must not disclose account email."""

from __future__ import annotations

import json

import pytest

from model_registry.models import Model

pytestmark = pytest.mark.django_db


@pytest.fixture
def public_model(model_obj):
    model_obj.is_public = True
    model_obj.save(update_fields=["is_public"])
    return model_obj


def test_anonymous_profile_does_not_expose_email(api_client, user, public_model):
    res = api_client.get(f"/api/users/@{user.username}/")

    assert res.status_code == 200
    assert "email" not in res.data
    assert user.email not in json.dumps(res.data, default=str)
    assert res.data["username"] == user.username
    assert res.data["total_public_models"] == 1


def test_anonymous_profile_is_unaffected_by_private_models(api_client, user, model_obj):
    res = api_client.get(f"/api/users/@{user.username}/")

    assert res.status_code == 200
    assert res.data["total_public_models"] == 0
    assert "email" not in res.data


def test_owner_still_sees_their_own_email_on_the_private_dashboard(
    auth_client, user, public_model
):
    res = auth_client.get("/api/dashboard/summary/")

    assert res.status_code == 200
    assert res.data["email"] == user.email


def test_non_owner_cannot_edit_a_model(auth_client, user2, public_model):
    res = auth_client.patch(
        f"/api/models/@{user2.username}/{public_model.name}/",
        {"description": "taken over"},
        format="json",
    )

    assert res.status_code in (403, 404)
    public_model.refresh_from_db()
    assert public_model.description == ""
