from decimal import Decimal
import pytest
from rest_framework.test import APIClient

from api_keys.models import APIKey, UniversalAPIKey
from billing.models import Wallet
from deployments.models import Deployment
from model_registry.models import Model, ModelVersion
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db


class DummySuccessRunner:
    def predict(self, payload):
        return RunnerResult(status_code=200, data={"predictions": [100]})


@pytest.fixture(autouse=True)
def mock_runner(monkeypatch):
    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: DummySuccessRunner(),
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner(django_user_model):
    user = django_user_model.objects.create_user(
        username="owner_user", email="owner@example.com", password="Pass123!Secure"
    )
    Wallet.objects.filter(user=user).update(credit_balance=Decimal("100.0"))
    return user


@pytest.fixture
def caller(django_user_model):
    user = django_user_model.objects.create_user(
        username="caller_user", email="caller@example.com", password="Pass123!Secure"
    )
    Wallet.objects.filter(user=user).update(credit_balance=Decimal("100.0"))
    return user


@pytest.fixture
def public_model(owner):
    m = Model.objects.create(name="pub-model", framework="sklearn", owner=owner, is_public=True, cost_per_run=Decimal("1"))
    v = ModelVersion.objects.create(model=m, version="v1", artifact_path="s3://m/v1")
    Deployment.objects.create(model_version=v, status=Deployment.Status.RUNNING, internal_url="http://runner:8000")
    return m


@pytest.fixture
def private_model(owner):
    m = Model.objects.create(name="priv-model", framework="sklearn", owner=owner, is_public=False, cost_per_run=Decimal("1"))
    v = ModelVersion.objects.create(model=m, version="v1", artifact_path="s3://m/v1")
    Deployment.objects.create(model_version=v, status=Deployment.Status.RUNNING, internal_url="http://runner:8000")
    return m


@pytest.fixture
def other_model(owner):
    m = Model.objects.create(name="other-model", framework="sklearn", owner=owner, is_public=True, cost_per_run=Decimal("1"))
    v = ModelVersion.objects.create(model=m, version="v1", artifact_path="s3://m/v1")
    Deployment.objects.create(model_version=v, status=Deployment.Status.RUNNING, internal_url="http://runner:8000")
    return m


# ---------------------------------------------------------------------------
# Direct Route: /api/predict/<model_id>/
# ---------------------------------------------------------------------------


def test_direct_predict_anonymous_rejected(api_client, public_model):
    res = api_client.post(f"/api/predict/{public_model.id}/", {"instances": [{"x": 1}]}, format="json")
    assert res.status_code == 401


def test_direct_predict_jwt_without_key_rejected(api_client, owner, public_model):
    api_client.force_authenticate(user=owner)
    res = api_client.post(f"/api/predict/{public_model.id}/", {"instances": [{"x": 1}]}, format="json")
    assert res.status_code == 403


def test_direct_predict_with_inactive_key_rejected(api_client, owner, public_model):
    key = APIKey.objects.create(user=owner, model=public_model, name="test-key", is_active=False)

    api_client.force_authenticate(user=owner)
    res = api_client.post(
        f"/api/predict/{public_model.id}/",
        {"instances": [{"x": 1}]},
        HTTP_X_API_KEY=key.raw_key,
        format="json",
    )
    assert res.status_code == 403


def test_direct_predict_with_wrong_model_key_rejected(api_client, owner, public_model, other_model):
    # Key created for other_model, attempted on public_model
    key = APIKey.objects.create(user=owner, model=other_model, name="other-key", is_active=True)

    api_client.force_authenticate(user=owner)
    res = api_client.post(
        f"/api/predict/{public_model.id}/",
        {"instances": [{"x": 1}]},
        HTTP_X_API_KEY=key.raw_key,
        format="json",
    )
    assert res.status_code == 403


def test_direct_predict_success(api_client, owner, public_model):
    key = APIKey.objects.create(user=owner, model=public_model, name="valid-key", is_active=True)

    api_client.force_authenticate(user=owner)
    res = api_client.post(
        f"/api/predict/{public_model.id}/",
        {"instances": [{"x": 1}]},
        HTTP_X_API_KEY=key.raw_key,
        format="json",
    )
    assert res.status_code == 200
    assert res.data["predictions"] == [100]


# ---------------------------------------------------------------------------
# Universal Route: /api/v1/inference/@<user>/<model>/
# ---------------------------------------------------------------------------


def test_universal_anonymous_rejected(api_client, owner, public_model):
    res = api_client.post(f"/api/v1/inference/@{owner.username}/{public_model.name}/", {"instances": [{"x": 1}]}, format="json")
    assert res.status_code in (401, 403)


def test_universal_public_model_caller_success(api_client, owner, caller, public_model):
    api_client.force_authenticate(user=caller)
    res = api_client.post(f"/api/v1/inference/@{owner.username}/{public_model.name}/", {"instances": [{"x": 1}]}, format="json")
    assert res.status_code == 200


def test_universal_private_model_non_owner_forbidden(api_client, owner, caller, private_model):
    api_client.force_authenticate(user=caller)
    res = api_client.post(f"/api/v1/inference/@{owner.username}/{private_model.name}/", {"instances": [{"x": 1}]}, format="json")
    assert res.status_code == 403
    assert res.data["code"] == "FORBIDDEN"


def test_universal_private_model_owner_allowed(api_client, owner, private_model):
    api_client.force_authenticate(user=owner)
    res = api_client.post(f"/api/v1/inference/@{owner.username}/{private_model.name}/", {"instances": [{"x": 1}]}, format="json")
    assert res.status_code == 200


def test_universal_api_key_auth_and_last_used(api_client, owner, caller, public_model):
    raw_key, prefix, hashed = UniversalAPIKey.generate()
    obj = UniversalAPIKey.objects.create(user=caller, name="test-universal", prefix=prefix, hashed_key=hashed)
    assert obj.last_used_at is None

    res = api_client.post(
        f"/api/v1/inference/@{owner.username}/{public_model.name}/",
        {"instances": [{"x": 1}]},
        HTTP_X_API_KEY=raw_key,
        format="json",
    )
    assert res.status_code == 200

    obj.refresh_from_db()
    assert obj.last_used_at is not None
