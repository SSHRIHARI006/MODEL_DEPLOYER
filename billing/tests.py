from decimal import Decimal

import pytest
from django.test import override_settings

from billing.models import LedgerTransaction, Wallet
from deployments.models import Deployment
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db


def login(api_client, email, password):
    res = api_client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    )
    assert res.status_code == 200
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    return api_client


def register(api_client, username):
    return api_client.post(
        "/api/auth/register/",
        {
            "username": username,
            "email": f"{username}@example.com",
            "password": "TestPass123!",
        },
        format="json",
    )


def predict(client, username, model_name):
    return client.post(
        f"/api/v1/inference/@{username}/{model_name}/",
        {"instances": [{"x": 1}]},
        format="json",
    )


@pytest.fixture
def public_model(model_obj):
    model_obj.is_public = True
    model_obj.save(update_fields=["is_public"])
    return model_obj


@pytest.fixture
def running_deployment(model_version):
    return Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://model_test:5000",
    )


@pytest.fixture
def dummy_runner(monkeypatch):
    class DummyRunner:
        def predict(self, payload):
            return RunnerResult(status_code=200, data={"predictions": [1]})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: DummyRunner(),
    )


def test_registration_grants_starting_credits(api_client):
    res = register(api_client, "fresh")
    assert res.status_code == 201
    wallet = Wallet.objects.get(user__username="fresh")
    assert wallet.credit_balance == Decimal("100")


@override_settings(BILLING_STARTING_CREDITS=Decimal("25"))
def test_starting_credits_configurable(api_client):
    res = register(api_client, "fresh")
    assert res.status_code == 201
    wallet = Wallet.objects.get(user__username="fresh")
    assert wallet.credit_balance == Decimal("25")


@override_settings(BILLING_ENABLED=False)
def test_no_wallet_created_when_billing_disabled(api_client):
    res = register(api_client, "fresh")
    assert res.status_code == 201
    assert not Wallet.objects.filter(user__username="fresh").exists()


def test_inference_charges_consumer_and_credits_creator(
    api_client, user, user2, public_model, running_deployment, dummy_runner
):
    login(api_client, "other@example.com", "TestPass123!")
    res = predict(api_client, user.username, public_model.name)

    assert res.status_code == 200

    consumer_wallet = Wallet.objects.get(user=user2)
    creator_wallet = Wallet.objects.get(user=user)
    assert consumer_wallet.credit_balance == Decimal("99")
    assert consumer_wallet.lifetime_spent == Decimal("1")
    assert creator_wallet.credit_balance == Decimal("101")
    assert creator_wallet.lifetime_earned == Decimal("1")

    transaction = LedgerTransaction.objects.get(
        transaction_type=LedgerTransaction.TransactionType.INFERENCE
    )
    assert transaction.amount == Decimal("1")
    assert transaction.consumer == user2
    assert transaction.creator == user


def test_insufficient_credits_returns_402(
    api_client, user, user2, public_model, running_deployment, dummy_runner
):
    Wallet.objects.filter(user=user2).update(credit_balance=Decimal("0"))
    login(api_client, "other@example.com", "TestPass123!")

    res = predict(api_client, user.username, public_model.name)

    assert res.status_code == 402
    assert res.data["error"] == "Insufficient credits"
    assert not LedgerTransaction.objects.exists()
    assert Wallet.objects.get(user=user2).credit_balance == Decimal("0")


@override_settings(BILLING_ENABLED=False)
def test_billing_disabled_skips_charge(
    api_client, user, user2, public_model, running_deployment, dummy_runner
):
    Wallet.objects.filter(user=user2).update(credit_balance=Decimal("0"))
    login(api_client, "other@example.com", "TestPass123!")

    res = predict(api_client, user.username, public_model.name)

    assert res.status_code == 200
    assert Wallet.objects.get(user=user2).credit_balance == Decimal("0")
    assert Wallet.objects.get(user=user).credit_balance == Decimal("100")
    assert not LedgerTransaction.objects.exists()


def test_no_payout_transaction_type():
    assert "PAYOUT" not in LedgerTransaction.TransactionType.values
    assert set(LedgerTransaction.TransactionType.values) == {"INFERENCE", "DEPOSIT"}
