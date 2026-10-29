from decimal import Decimal
import pytest
from rest_framework.test import APIClient

from billing.models import LedgerTransaction, Wallet
from deployments.models import Deployment
from model_registry.models import Model, ModelVersion
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def creator(django_user_model):
    return django_user_model.objects.create_user(
        username="model_creator", email="creator@example.com", password="Pass123!Secure"
    )


@pytest.fixture
def consumer(django_user_model):
    return django_user_model.objects.create_user(
        username="model_consumer", email="consumer@example.com", password="Pass123!Secure"
    )


@pytest.fixture
def paid_model(creator):
    model = Model.objects.create(
        name="premium-model",
        framework="sklearn",
        task_type="regression",
        owner=creator,
        is_public=True,
        cost_per_run=Decimal("10.0000"),
    )
    v1 = ModelVersion.objects.create(
        model=model,
        version="v1",
        artifact_path="s3://models/v1",
        status="READY",
    )
    Deployment.objects.create(
        model_version=v1,
        status=Deployment.Status.RUNNING,
        internal_url="http://runner:8000",
    )
    return model


class DummySuccessRunner:
    def predict(self, payload):
        return RunnerResult(status_code=200, data={"predictions": [42]})


class DummyFailingRunner:
    def predict(self, payload):
        return RunnerResult(status_code=500, data={"error": "Model computation failed"})


class DummyCrashingRunner:
    def predict(self, payload):
        raise RuntimeError("Out of memory in runner worker")


def test_creator_using_own_model_is_free(api_client, creator, paid_model, monkeypatch):
    """BILL-01: Creator == consumer is charged 0 credits."""
    monkeypatch.setattr("prediction_gateway.views.RunnerFactory.get_runner", lambda framework: DummySuccessRunner())
    Wallet.objects.filter(user=creator).update(credit_balance=Decimal("100.0000"))

    api_client.force_authenticate(user=creator)
    res = api_client.post(
        f"/api/v1/inference/@{creator.username}/{paid_model.name}/",
        {"instances": [{"x": 1}]},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["predictions"] == [42]

    # No wallet deduction or transaction
    creator_wallet = Wallet.objects.get(user=creator)
    assert creator_wallet.credit_balance == Decimal("100.0000")
    assert not LedgerTransaction.objects.exists()


def test_failed_inference_refunds_100_percent(api_client, creator, consumer, paid_model, monkeypatch):
    """BILL-01: Upfront debit is refunded 100% on runner computation failure with reference_id."""
    monkeypatch.setattr("prediction_gateway.views.RunnerFactory.get_runner", lambda framework: DummyFailingRunner())

    Wallet.objects.filter(user=consumer).update(credit_balance=Decimal("50.0000"))
    Wallet.objects.filter(user=creator).update(credit_balance=Decimal("100.0000"))

    api_client.force_authenticate(user=consumer)
    res = api_client.post(
        f"/api/v1/inference/@{creator.username}/{paid_model.name}/",
        {"instances": [{"x": 1}]},
        format="json",
    )
    assert res.status_code == 500

    # Balances restored
    c_wallet = Wallet.objects.get(user=consumer)
    m_wallet = Wallet.objects.get(user=creator)
    assert c_wallet.credit_balance == Decimal("50.0000")
    assert m_wallet.credit_balance == Decimal("100.0000")

    # Verify both transactions: INFERENCE debit and REFUND with reference_id
    txs = list(LedgerTransaction.objects.filter(consumer=consumer, creator=creator).order_by("timestamp"))
    assert len(txs) == 2
    debit_tx, refund_tx = txs[0], txs[1]

    assert debit_tx.transaction_type == LedgerTransaction.TransactionType.INFERENCE
    assert debit_tx.amount == Decimal("10.0000")

    assert refund_tx.transaction_type == LedgerTransaction.TransactionType.REFUND
    assert refund_tx.amount == Decimal("10.0000")
    assert refund_tx.reference_id == str(debit_tx.id)


def test_crashing_inference_runner_refunds_100_percent(api_client, creator, consumer, paid_model, monkeypatch):
    """BILL-01: Upfront debit is refunded 100% on unhandled runner crash."""
    monkeypatch.setattr("prediction_gateway.views.RunnerFactory.get_runner", lambda framework: DummyCrashingRunner())

    Wallet.objects.filter(user=consumer).update(credit_balance=Decimal("50.0000"))
    Wallet.objects.filter(user=creator).update(credit_balance=Decimal("100.0000"))

    api_client.force_authenticate(user=consumer)
    res = api_client.post(
        f"/api/v1/inference/@{creator.username}/{paid_model.name}/",
        {"instances": [{"x": 1}]},
        format="json",
    )
    assert res.status_code == 500
    assert res.data["code"] == "INFERENCE_FAILED"

    c_wallet = Wallet.objects.get(user=consumer)
    m_wallet = Wallet.objects.get(user=creator)
    assert c_wallet.credit_balance == Decimal("50.0000")
    assert m_wallet.credit_balance == Decimal("100.0000")

    refund_tx = LedgerTransaction.objects.filter(transaction_type=LedgerTransaction.TransactionType.REFUND).first()
    assert refund_tx is not None
    assert refund_tx.amount == Decimal("10.0000")


def test_cache_hit_applies_50_percent_discount_refund(api_client, creator, consumer, paid_model, monkeypatch):
    """BILL-01: Cache hits receive a 50% discount refund."""
    monkeypatch.setattr("prediction_gateway.views.RunnerFactory.get_runner", lambda framework: DummySuccessRunner())

    Wallet.objects.filter(user=consumer).update(credit_balance=Decimal("50.0000"))
    Wallet.objects.filter(user=creator).update(credit_balance=Decimal("100.0000"))

    api_client.force_authenticate(user=consumer)

    # First call: Cold inference -> charges full 10.0
    payload = {"instances": [{"feature": 99}]}
    res1 = api_client.post(f"/api/v1/inference/@{creator.username}/{paid_model.name}/", payload, format="json")
    assert res1.status_code == 200

    c_wallet = Wallet.objects.get(user=consumer)
    m_wallet = Wallet.objects.get(user=creator)
    assert c_wallet.credit_balance == Decimal("40.0000")
    assert m_wallet.credit_balance == Decimal("110.0000")

    # Second call: Cache hit -> reserves 10.0, detects cache hit, refunds 5.0 (net charge: 5.0)
    res2 = api_client.post(f"/api/v1/inference/@{creator.username}/{paid_model.name}/", payload, format="json")
    assert res2.status_code == 200

    c_wallet.refresh_from_db()
    m_wallet.refresh_from_db()
    # Net balance after second call: 40 - 5 = 35; creator: 110 + 5 = 115
    assert c_wallet.credit_balance == Decimal("35.0000")
    assert m_wallet.credit_balance == Decimal("115.0000")

    # Verify refund ledger transaction
    refund_tx = LedgerTransaction.objects.filter(
        consumer=consumer, transaction_type=LedgerTransaction.TransactionType.REFUND
    ).first()
    assert refund_tx is not None
    assert refund_tx.amount == Decimal("5.0000")
    assert refund_tx.reference_id is not None
