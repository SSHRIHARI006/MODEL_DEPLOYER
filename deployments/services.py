from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time

from django.db import transaction
from django.utils import timezone

from runners.factory import RunnerFactory

from .models import Deployment


_executor = ThreadPoolExecutor(max_workers=2)


def start_deployment_async(deployment_id: str):
    _executor.submit(_build_and_run_deployment, deployment_id)


def _build_and_run_deployment(deployment_id: str):
    deployment = Deployment.objects.select_related("model_version").get(
        id=deployment_id
    )

    try:
        with transaction.atomic():
            deployment.transition_to(Deployment.Status.BUILDING)
            deployment.last_error = None
            deployment.build_logs = None
            deployment.save(
                update_fields=["status", "last_error", "build_logs", "updated_at"]
            )

        build_path = Path(deployment.model_version.artifact_path)
        if not build_path.exists() or not build_path.is_dir():
            raise RuntimeError("Model artifact path does not exist")

        model = deployment.model_version.model
        runner = RunnerFactory.get_runner(framework=model.framework)

        manifest_path = build_path / "model.yaml"
        init_result = runner.init_environment(
            {
                "model_id": str(model.id),
                "manifest_path": str(manifest_path),
            }
        )
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
            raise RuntimeError("Runner healthcheck timed out")

        deployment.refresh_from_db()
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
    except Exception as e:
        deployment.refresh_from_db()
        if deployment.status in (Deployment.Status.PENDING, Deployment.Status.BUILDING):
            deployment.transition_to(Deployment.Status.FAILED)
        deployment.last_error = str(e)
        deployment.save(update_fields=["status", "last_error", "updated_at"])
