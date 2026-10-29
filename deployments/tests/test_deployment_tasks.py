from unittest.mock import patch

import pytest

from deployments.models import Deployment
from deployments.services import RetryableDeploymentError
from deployments.tasks import build_deployment
from runners.base import RunnerResult

pytestmark = pytest.mark.django_db


def test_build_deployment_is_idempotent_for_running_deployment(model_version):
    deployment = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.RUNNING,
        internal_url="http://worker:8002",
    )

    with patch("deployments.tasks._build_and_run_deployment") as build:
        result = build_deployment.apply(args=[str(deployment.id)]).get()

    assert result["status"] == "running"
    build.assert_not_called()


def test_build_deployment_marks_deterministic_failures(model_version):
    deployment = Deployment.objects.create(model_version=model_version)

    with patch(
        "deployments.tasks._build_and_run_deployment",
        side_effect=RuntimeError("bad manifest"),
    ):
        result = build_deployment.apply(args=[str(deployment.id)]).get()

    deployment.refresh_from_db()
    assert result["status"] == "failed"
    assert deployment.status == Deployment.Status.FAILED
    assert deployment.last_error == "bad manifest"


def test_build_deployment_retries_transient_failures(model_version):
    deployment = Deployment.objects.create(model_version=model_version)

    with patch(
        "deployments.tasks._build_and_run_deployment",
        side_effect=RetryableDeploymentError("runner unavailable"),
    ), patch.object(build_deployment, "retry", side_effect=RuntimeError("retry")) as retry:
        with pytest.raises(RuntimeError, match="retry"):
            build_deployment.apply(args=[str(deployment.id)]).get(propagate=True)

    retry.assert_called_once()
    deployment.refresh_from_db()
    assert deployment.status == Deployment.Status.PENDING


def test_build_deployment_transitions_to_running(model_version, tmp_path):
    deployment = Deployment.objects.create(
        model_version=model_version,
        status=Deployment.Status.PENDING,
    )
    model_version.artifact_path = str(tmp_path)
    model_version.save(update_fields=["artifact_path"])

    class Runner:
        base_url = "http://worker:8002"
        init_payload = None

        def init_environment(self, payload):
            self.init_payload = payload
            return RunnerResult(status_code=200, data={})

        def healthcheck(self):
            return RunnerResult(status_code=200, data={})

    runner = Runner()
    with patch("deployments.services.RunnerFactory.get_runner", return_value=runner):
        result = build_deployment.apply(args=[str(deployment.id)]).get()

    deployment.refresh_from_db()
    assert result["status"] == "running"
    assert deployment.status == Deployment.Status.RUNNING
    assert deployment.internal_url == "http://worker:8002"
    assert runner.init_payload["model_id"] == str(model_version.id)
