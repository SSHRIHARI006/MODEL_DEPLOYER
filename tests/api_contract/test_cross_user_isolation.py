from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from deployments.models import Deployment
from api_keys.models import APIKey, UniversalAPIKey
from billing.models import Wallet

pytestmark = pytest.mark.django_db


def get_auth_client(user, password="TestPass123!"):
    client = APIClient()
    res = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": password},
        format="json",
    )
    token = res.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_user_cannot_view_or_stop_or_delete_other_user_deployment(db, user, user2, model_version):
    """User B cannot view, stop, or delete User A's deployment."""
    client_a = get_auth_client(user)
    client_b = get_auth_client(user2)

    # User A creates a deployment
    dep = Deployment.objects.create(
        model_version=model_version,
        status="RUNNING",
        internal_url="http://runner:8001",
    )

    # User A sees it
    res_a = client_a.get("/api/deployments/")
    assert res_a.status_code == 200
    dep_ids_a = [d["id"] for d in res_a.data]
    assert str(dep.id) in dep_ids_a

    # User B does NOT see User A's deployment in their list
    res_b = client_b.get("/api/deployments/")
    assert res_b.status_code == 200
    dep_ids_b = [d["id"] for d in res_b.data]
    assert str(dep.id) not in dep_ids_b

    # User B cannot GET the deployment directly
    res_get_b = client_b.get(f"/api/deployments/{dep.id}/")
    assert res_get_b.status_code == 404

    # User B cannot STOP the deployment
    res_stop_b = client_b.post(f"/api/deployments/{dep.id}/stop/")
    assert res_stop_b.status_code == 404

    # User B cannot DELETE the deployment
    res_del_b = client_b.delete(f"/api/deployments/{dep.id}/")
    assert res_del_b.status_code == 404


def test_user_cannot_modify_or_delete_other_user_model(db, user, user2, model_obj):
    """User B cannot modify (PATCH) or DELETE User A's model."""
    client_b = get_auth_client(user2)

    # User B cannot PATCH User A's model
    res_patch = client_b.patch(
        f"/api/models/@{user.username}/{model_obj.name}/",
        {"description": "hacked by user2"},
        format="json",
    )
    assert res_patch.status_code in [403, 404]

    # User B cannot DELETE User A's model
    res_del = client_b.delete(f"/api/models/{model_obj.id}/")
    assert res_del.status_code == 404


def test_user_cannot_view_or_deactivate_other_user_api_key(db, user, user2, model_obj):
    """User B cannot view or deactivate User A's model API key."""
    client_b = get_auth_client(user2)

    key_a = APIKey.objects.create(user=user, model=model_obj, name="key-a")

    # User B list keys does not include key_a
    res_list = client_b.get("/api/keys/")
    assert res_list.status_code == 200
    key_ids = [k["id"] for k in res_list.data]
    assert str(key_a.id) not in key_ids

    # User B cannot deactivate key_a
    res_deact = client_b.post(f"/api/keys/{key_a.id}/deactivate/")
    assert res_deact.status_code == 404


def test_user_cannot_view_or_delete_other_user_universal_key(db, user, user2):
    """User B cannot view or delete User A's universal API key."""
    client_b = get_auth_client(user2)

    _raw, prefix, hashed = UniversalAPIKey.generate()
    uni_key_a = UniversalAPIKey.objects.create(
        user=user,
        name="uni-a",
        prefix=prefix,
        hashed_key=hashed,
    )

    # User B universal list does not include uni_key_a
    res_list = client_b.get("/api/keys/universal/")
    assert res_list.status_code == 200
    key_ids = [k["id"] for k in res_list.data]
    assert str(uni_key_a.id) not in key_ids

    # User B cannot delete uni_key_a
    res_del = client_b.delete(f"/api/keys/universal/{uni_key_a.id}/")
    assert res_del.status_code == 404


def test_wallet_isolation(db, user, user2):
    """User B's wallet view shows only User B's balance."""
    wallet_a = Wallet.objects.get_or_create(user=user)[0]
    wallet_a.credit_balance = 500
    wallet_a.save()

    wallet_b = Wallet.objects.get_or_create(user=user2)[0]
    wallet_b.credit_balance = 10
    wallet_b.save()

    client_b = get_auth_client(user2)
    res_b = client_b.get("/api/wallet/")
    assert res_b.status_code == 200
    assert float(res_b.data["wallet"]["credit_balance"]) == 10.0
