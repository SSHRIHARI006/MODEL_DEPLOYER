from __future__ import annotations

import concurrent.futures
import pytest
from rest_framework.test import APIClient
from django.db import IntegrityError, transaction

from deployments.models import Deployment
from model_registry.models import Model, ModelVersion
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db(transaction=True)


def test_sequential_repeat_identical_results(auth_client, model_obj, model_version, monkeypatch):
    """3E: Sequential repeated requests to the same model return identical results."""
    call_count = 0

    class CountingRunner:
        def predict(self, payload):
            nonlocal call_count
            call_count += 1
            # Return predictable deterministic output
            return RunnerResult(status_code=200, data={"predictions": [42.0]})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: CountingRunner(),
    )

    Deployment.objects.create(
        model_version=model_version,
        status="RUNNING",
        internal_url="http://runner:8001",
    )

    res_key = auth_client.post("/api/keys/", {"model_id": model_obj.id, "name": "seq-key"}, format="json")
    api_key = res_key.data["key"]

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key,
    )

    payload = {"instances": [{"x": 1.0}]}
    r1 = auth_client.post(f"/api/predict/{model_obj.id}/", payload, format="json")
    r2 = auth_client.post(f"/api/predict/{model_obj.id}/", payload, format="json")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.data == r2.data


def test_concurrent_distinct_payloads_no_contamination(auth_client, model_obj, model_version, monkeypatch):
    """3E: Concurrent requests with distinct inputs return corresponding outputs without contamination."""
    class EchoRunner:
        def predict(self, payload):
            instances = payload.get("instances", [])
            val = instances[0].get("id") if instances else -1
            return RunnerResult(status_code=200, data={"predictions": [val * 2]})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: EchoRunner(),
    )

    Deployment.objects.create(
        model_version=model_version,
        status="RUNNING",
        internal_url="http://runner:8001",
    )

    res_key = auth_client.post("/api/keys/", {"model_id": model_obj.id, "name": "c-key"}, format="json")
    api_key = res_key.data["key"]

    auth_header = auth_client._credentials["HTTP_AUTHORIZATION"]

    def run_call(val: int):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=auth_header, HTTP_X_API_KEY=api_key)
        res = client.post(
            f"/api/predict/{model_obj.id}/",
            {"instances": [{"id": val}]},
            format="json",
        )
        return val, res.status_code, res.data.get("predictions")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_call, i) for i in range(1, 11)]
        for f in concurrent.futures.as_completed(futures):
            val, code, preds = f.result()
            assert code == 200
            assert preds == [val * 2], f"Cross-contamination: expected {[val * 2]}, got {preds}"


def test_duplicate_deployment_concurrency_guard(model_version):
    """3E: Concurrent deployment creation cannot violate single active deployment invariant."""
    # Create first active deployment
    Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
    )

    # Attempting to insert another active deployment violates the unique constraint
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Deployment.objects.create(
                model_version=model_version,
                status=Deployment.Status.BUILDING,
            )
