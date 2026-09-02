from __future__ import annotations

from pathlib import Path
import time

from django.db import transaction
from django.utils import timezone

from runners.factory import RunnerFactory

from .models import Deployment


class RetryableDeploymentError(RuntimeError):
    pass


class DeploymentCancelledError(RuntimeError):
    pass


def start_deployment_async(deployment_id: str):
    from .tasks import build_deployment

    return build_deployment.delay(deployment_id)


def _build_and_run_deployment(deployment_id: str):
    with transaction.atomic():
        deployment = Deployment.objects.select_for_update().select_related(
            "model_version__model"
        ).get(id=deployment_id)
        if deployment.status in (Deployment.Status.RUNNING, Deployment.Status.STOPPED):
            return
        if deployment.status == Deployment.Status.PENDING:
            deployment.transition_to(Deployment.Status.BUILDING)
            deployment.last_error = None
            deployment.build_logs = None
            deployment.save(
                update_fields=["status", "last_error", "build_logs", "updated_at"]
            )
        elif deployment.status != Deployment.Status.BUILDING:
            raise RuntimeError(f"Cannot build deployment in state {deployment.status}")

    base_path = deployment.model_version.artifact_path
    if base_path.startswith("s3://"):
        manifest_path = f"{base_path}/model.yaml"
    else:
        build_path = Path(base_path)
        if not build_path.exists() or not build_path.is_dir():
            raise RuntimeError("Model artifact path does not exist")
        manifest_path = str(build_path / "model.yaml")

    model = deployment.model_version.model
    runner = RunnerFactory.get_runner(framework=model.framework)

    init_result = runner.init_environment(
        {
            "model_id": str(model.id),
            "manifest_path": manifest_path,
        }
    )
    if init_result.status_code >= 500:
        raise RetryableDeploymentError(init_result.data)
    if init_result.status_code >= 400:
        raise RuntimeError(init_result.data)

    deadline = time.time() + 60
    health_ok = False
    while time.time() < deadline:
        health_result = runner.healthcheck()
        if health_result.status_code == 200:
            health_ok = True
            break
        time.sleep(0.5)

    if not health_ok:
        raise RetryableDeploymentError("Runner healthcheck timed out")

    with transaction.atomic():
        deployment = Deployment.objects.select_for_update().select_related(
            "model_version"
        ).get(id=deployment_id)
        if deployment.status == Deployment.Status.STOPPED:
            raise DeploymentCancelledError("Deployment was stopped during startup")
        if deployment.status != Deployment.Status.BUILDING:
            raise RuntimeError(
                f"Deployment changed state during build: {deployment.status}"
            )
        deployment.transition_to(Deployment.Status.RUNNING)
        deployment.image_name = None
        deployment.container_name = None
        deployment.container_id = None
        deployment.internal_url = runner.base_url
        deployment.endpoint_url = None
        deployment.build_logs = None
        deployment.started_at = timezone.now()
        deployment.save(
            update_fields=[
                "status",
                "image_name",
                "container_name",
                "container_id",
                "internal_url",
                "endpoint_url",
                "build_logs",
                "started_at",
                "updated_at",
            ]
        )
