import pytest
from model_registry.models import Model
from django.contrib.auth import get_user_model

User = get_user_model()
pytestmark = pytest.mark.django_db


def test_delete_model_requires_auth(api_client):
    res = api_client.delete("/api/models/some-id/")
    assert res.status_code == 401


def test_delete_model_success(auth_client, user):
    model = Model.objects.create(
        id="d9b12663-e4ee-477e-9287-007cddfeb510",
        name="test-model",
        framework="sklearn",
        owner=user,
    )
    assert Model.objects.filter(id=model.id).exists()

    res = auth_client.delete(f"/api/models/{model.id}/")
    assert res.status_code == 200
    assert not Model.objects.filter(id=model.id).exists()


def test_delete_model_not_found(auth_client):
    res = auth_client.delete("/api/models/non-existent-id/")
    assert res.status_code == 404


def test_delete_model_cannot_delete_others(auth_client):
    other_user = User.objects.create_user(
        email="other@example.com", password="password"
    )
    model = Model.objects.create(
        id="89b12663-e4ee-477e-9287-007cddfeb519",
        name="other-model",
        framework="sklearn",
        owner=other_user,
    )

    res = auth_client.delete(f"/api/models/{model.id}/")
    assert res.status_code == 404
    assert Model.objects.filter(id=model.id).exists()
