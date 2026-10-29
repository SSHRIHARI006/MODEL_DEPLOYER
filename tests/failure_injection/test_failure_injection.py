from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status

from core.runner_errors import RUNNER_CODE_WORKER_TIMEOUT
from deployments.models import Deployment
from runners.base import RunnerResult

pytestmark = [pytest.mark.django_db, pytest.mark.failure_injection]


def test_runner_killed_during_inference(auth_client, model_obj, model_version, monkeypatch):
    """TEST-02 / 3F: Runner killed / connection reset during inference maps to 502 and records failure."""
    class CrashingRunner:
        def predict(self, payload):
            raise requests.ConnectionError("Connection refused by runner process")

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: CrashingRunner(),
    )

    Deployment.objects.create(
        model_version=model_version,
        status="RUNNING",
        internal_url="http://runner:8001",
    )

    res_key = auth_client.post("/api/keys/", {"model_id": model_obj.id, "name": "fail-key"}, format="json")
    api_key = res_key.data["key"]

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key,
    )

    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1.0}]},
        format="json",
    )
    assert res.status_code == status.HTTP_502_BAD_GATEWAY
    assert "error" in res.data


def test_runner_inference_timeout(auth_client, model_obj, model_version, monkeypatch):
    """TEST-02 / 3F: Runner inference hanging beyond timeout returns 504 cleanly."""
    class HangingRunner:
        def predict(self, payload):
            raise requests.Timeout("Runner inference timed out")

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: HangingRunner(),
    )

    Deployment.objects.create(
        model_version=model_version,
        status="RUNNING",
        internal_url="http://runner:8001",
    )

    res_key = auth_client.post("/api/keys/", {"model_id": model_obj.id, "name": "timeout-key"}, format="json")
    api_key = res_key.data["key"]

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key,
    )

    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1.0}]},
        format="json",
    )
    assert res.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert "timed out" in res.data["error"].lower()


def test_redis_unavailable_during_prediction_graceful_fallback(
    auth_client, model_obj, model_version, monkeypatch
):
    """TEST-02 / 3F: Prediction gateway degrades gracefully if Redis cache is unavailable."""
    class WorkingRunner:
        def predict(self, payload):
            return RunnerResult(status_code=200, data={"predictions": [123.45]})

    monkeypatch.setattr(
        "prediction_gateway.views.RunnerFactory.get_runner",
        lambda framework: WorkingRunner(),
    )

    # Simulate Redis connection failure on cache
    def broken_cache_get(*args, **kwargs):
        raise ConnectionError("Redis connection refused: 6379")

    def broken_cache_set(*args, **kwargs):
        raise ConnectionError("Redis connection refused: 6379")

    monkeypatch.setattr("django.core.cache.cache.get", broken_cache_get)
    monkeypatch.setattr("django.core.cache.cache.set", broken_cache_set)

    Deployment.objects.create(
        model_version=model_version,
        status="RUNNING",
        internal_url="http://runner:8001",
    )

    res_key = auth_client.post("/api/keys/", {"model_id": model_obj.id, "name": "cache-fail-key"}, format="json")
    api_key = res_key.data["key"]

    auth_client.credentials(
        HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
        HTTP_X_API_KEY=api_key,
    )

    # Request must succeed despite broken Redis
    res = auth_client.post(
        f"/api/predict/{model_obj.id}/",
        {"instances": [{"x": 1.0}]},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["predictions"] == [123.45]


def test_minio_unavailable_during_upload_cleanup(auth_client, user, monkeypatch):
    """TEST-02 / 3F: MinIO failure during upload cleans up local temp files and returns safe 500."""
    user.can_upload_models = True
    user.save()

    mock_s3 = MagicMock()
    mock_s3.upload_file.side_effect = ConnectionError("MinIO connection refused")
    monkeypatch.setattr("model_registry.views.get_s3_client", lambda: mock_s3)

    yaml_manifest = """
name: minio_fail_model
framework: sklearn
python_version: "3.12"
requirements: requirements.txt
model_artifact: model.pkl
task_type: regression
""".strip()

    import io
    import zipfile
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("model.yaml", yaml_manifest)
        zf.writestr("requirements.txt", "scikit-learn==1.8.0\n")
        zf.writestr("model.pkl", b"dummy")

    upload = SimpleUploadedFile("model.zip", bio.getvalue(), content_type="application/zip")
    res = auth_client.post("/api/models/upload/", {"file": upload}, format="multipart")

    assert res.status_code == 500
    assert res.data["code"] == "UPLOAD_FAILED"
    assert "request_id" in res.data


def test_stale_build_reaping(model_version):
    """TEST-02 / 3F: Celery task killed mid-build is reaped by reap_stale_builds command."""
    from django.core.management import call_command

    stale_dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.BUILDING,
        celery_task_id="dead-task-1234",
    )
    # Manually backdate created_at and updated_at
    past_time = timezone.now() - timezone.timedelta(minutes=15)
    Deployment.objects.filter(id=stale_dep.id).update(created_at=past_time, updated_at=past_time)

    # Call reap_stale_builds with 10-minute threshold
    call_command("reap_stale_builds", threshold_minutes=10)

    stale_dep.refresh_from_db()
    assert stale_dep.status == Deployment.Status.FAILED
    assert stale_dep.last_error_code == RUNNER_CODE_WORKER_TIMEOUT
