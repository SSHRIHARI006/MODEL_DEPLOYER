import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from model_registry.models import Model, ModelVersion
from api_keys.models import APIKey

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="test@example.com", password="TestPass123!")


@pytest.fixture
def user2(db):
    return User.objects.create_user(email="other@example.com", password="TestPass123!")


@pytest.fixture
def auth_client(api_client, user):
    res = api_client.post(
        "/api/auth/login/",
        {"email": "test@example.com", "password": "TestPass123!"},
        format="json",
    )
    token = res.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def model_obj(db, user):
    return Model.objects.create(
        id="model-test-1",
        name="M1",
        framework="sklearn",
        task_type="regression",
        owner=user,
    )


@pytest.fixture
def model_obj_user2(db, user2):
    return Model.objects.create(
        id="model-test-2",
        name="M2",
        framework="sklearn",
        task_type="regression",
        owner=user2,
    )


@pytest.fixture
def model_version(db, model_obj):
    return ModelVersion.objects.create(
        model=model_obj,
        version="v1",
        artifact_path="/tmp/dummy-artifacts",
        status="READY",
    )


@pytest.fixture
def api_key(db, user, model_obj):
    return APIKey.objects.create(user=user, model=model_obj, name="test-key")