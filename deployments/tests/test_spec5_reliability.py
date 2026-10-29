from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.runner_errors import (
    RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE,
    RUNNER_CODE_MODEL_LOAD_FAILED,
    RUNNER_CODE_WORKER_TIMEOUT,
    RUNNER_CODE_WORKER_UNAVAILABLE,
)
from deployments.models import Deployment
from deployments.services import (
    NonRetryableDeploymentError,
    RetryableDeploymentError,
    _build_and_run_deployment,
)
from deployments.tasks import build_deployment
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db


def test_duplicate_active_deployment_blocked(auth_client, model_version):
    """REL-07: Creating a second active deployment for the same version returns 409."""
    # First active deployment
    dep1 = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.BUILDING,
    )

    res = auth_client.post(
        "/api/deployments/",
        {"model_version_id": str(model_version.id)},
        format="json",
    )
    assert res.status_code == 409
    assert res.data["deployment_id"] == str(dep1.id)
    assert res.data["status"] == Deployment.Status.BUILDING


def test_deployment_can_be_created_after_previous_failed_or_stopped(
    auth_client, model_version
):
    """REL-07: Terminal deployments (FAILED, STOPPED) do not block new builds."""
    dep_failed = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.FAILED,
    )

    with patch("deployments.views.start_deployment_async"):
        res = auth_client.post(
            "/api/deployments/",
            {"model_version_id": str(model_version.id)},
            format="json",
        )
    assert res.status_code == 202
    assert res.data["status"] == Deployment.Status.PENDING
    assert res.data["id"] != str(dep_failed.id)


def test_stop_deployment_endpoint(auth_client, model_version):
    """REL-09: POST /api/deployments/<id>/stop/ stops the deployment and triggers teardown."""
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
    )

    mock_runner = MagicMock()
    with patch("deployments.views.RunnerFactory.get_runner", return_value=mock_runner):
        res = auth_client.post(f"/api/deployments/{dep.id}/stop/")

    assert res.status_code == 200
    assert res.data["status"] == Deployment.Status.STOPPED
    assert res.data["stopped_at"] is not None
    mock_runner.teardown.assert_called_once_with({"model_id": str(model_version.id)})

    # Idempotent second call
    res2 = auth_client.post(f"/api/deployments/{dep.id}/stop/")
    assert res2.status_code == 200
    assert res2.data["status"] == Deployment.Status.STOPPED


def test_delete_deployment_endpoint(auth_client, model_version):
    """REL-09: DELETE /api/deployments/<id>/ stops and tears down runner before deletion."""
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
    )

    mock_runner = MagicMock()
    with patch("deployments.views.RunnerFactory.get_runner", return_value=mock_runner):
        res = auth_client.delete(f"/api/deployments/{dep.id}/")

    assert res.status_code == 200
    mock_runner.teardown.assert_called_once()
    assert not Deployment.objects.filter(id=dep.id).exists()


def test_reap_stale_builds_management_command(model_version):
    """REL-06: Stale BUILDING rows older than the threshold are reaped to FAILED."""
    stale_dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.BUILDING,
    )
    # Artificially age the record
    Deployment.objects.filter(id=stale_dep.id).update(
        updated_at=timezone.now() - timedelta(minutes=45)
    )

    fresh_dep = Deployment.objects.create(
        model_version=model_version.model.versions.create(version="v2", status="READY"),
        status=Deployment.Status.BUILDING,
    )

    call_command("reap_stale_builds", threshold_minutes=30)

    stale_dep.refresh_from_db()
    fresh_dep.refresh_from_db()

    assert stale_dep.status == Deployment.Status.FAILED
    assert stale_dep.last_error_code == RUNNER_CODE_WORKER_TIMEOUT
    assert "reaped: stale BUILDING state" in stale_dep.last_error

    assert fresh_dep.status == Deployment.Status.BUILDING


def test_error_classification_deterministic_failures_not_retried(model_version, tmp_path):
    """REL-02: Deterministic runner errors raise NonRetryableDeploymentError and store code."""
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.PENDING,
    )
    model_version.artifact_path = str(tmp_path)
    model_version.save(update_fields=["artifact_path"])

    class DeterministicFailRunner:
        base_url = "http://worker:8002"
        healthcheck_timeout_seconds = 5

        def init_environment(self, payload):
            return RunnerResult(
                status_code=500,
                data={
                    "detail": {
                        "code": RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE,
                        "error": "No matching distribution found for bad-pkg",
                        "retryable": False,
                    }
                },
            )

    with patch("deployments.services.RunnerFactory.get_runner", return_value=DeterministicFailRunner()):
        with pytest.raises(NonRetryableDeploymentError) as exc_info:
            _build_and_run_deployment(str(dep.id))

        assert exc_info.value.code == RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE


def test_error_classification_transient_failures_retryable(model_version, tmp_path):
    """REL-02: Transient runner errors raise RetryableDeploymentError and store code."""
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.PENDING,
    )
    model_version.artifact_path = str(tmp_path)
    model_version.save(update_fields=["artifact_path"])

    class TransientFailRunner:
        base_url = "http://worker:8002"
        healthcheck_timeout_seconds = 5

        def init_environment(self, payload):
            return RunnerResult(
                status_code=503,
                data={
                    "detail": {
                        "code": RUNNER_CODE_WORKER_UNAVAILABLE,
                        "error": "Temporary network resolution failure",
                        "retryable": True,
                    }
                },
            )

    with patch("deployments.services.RunnerFactory.get_runner", return_value=TransientFailRunner()):
        with pytest.raises(RetryableDeploymentError) as exc_info:
            _build_and_run_deployment(str(dep.id))

        assert exc_info.value.code == RUNNER_CODE_WORKER_UNAVAILABLE


def test_celery_task_records_task_id_and_attempt(model_version, tmp_path):
    """REL-06: Celery build task records celery_task_id and build_attempt on deployment."""
    dep = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.PENDING,
    )
    model_version.artifact_path = str(tmp_path)
    model_version.save(update_fields=["artifact_path"])

    class SuccessRunner:
        base_url = "http://worker:8002"
        healthcheck_timeout_seconds = 5

        def init_environment(self, payload):
            return RunnerResult(status_code=200, data={})

        def readiness(self):
            return RunnerResult(status_code=200, data={"status": "ready"})

    with patch("deployments.services.RunnerFactory.get_runner", return_value=SuccessRunner()):
        result = build_deployment.apply(args=[str(dep.id)]).get()

    dep.refresh_from_db()
    assert result["status"] == "running"
    assert dep.celery_task_id is not None
    assert dep.build_attempt == 1
    assert dep.status == Deployment.Status.RUNNING
