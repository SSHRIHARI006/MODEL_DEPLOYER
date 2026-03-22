import pytest
from api_keys.models import APIKey

pytestmark = pytest.mark.django_db


def test_create_api_key_for_own_model(auth_client, model_obj):
    res = auth_client.post("/api/keys/", {"model_id": model_obj.id, "name": "k1"}, format="json")
    assert res.status_code == 201
    assert "key" in res.data


def test_create_api_key_for_other_user_model_forbidden(auth_client, model_obj_user2):
    res = auth_client.post("/api/keys/", {"model_id": model_obj_user2.id, "name": "bad"}, format="json")
    assert res.status_code in (403, 404)


def test_list_only_own_api_keys(auth_client, api_key, user2, model_obj_user2):
    APIKey.objects.create(user=user2, model=model_obj_user2, name="other-user-key")
    res = auth_client.get("/api/keys/")
    assert res.status_code == 200
    assert all(item["model_id"] == api_key.model_id for item in res.data)


def test_deactivate_key(auth_client, api_key):
    res = auth_client.post(f"/api/keys/{api_key.id}/deactivate/")
    assert res.status_code == 200
    api_key.refresh_from_db()
    assert api_key.is_active is False