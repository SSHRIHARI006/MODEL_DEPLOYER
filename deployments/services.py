from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from core import container_manager

from .models import Deployment


_executor = ThreadPoolExecutor(max_workers=2)


def start_deployment_async(deployment_id: str):
    _executor.submit(_build_and_run_deployment, deployment_id)


def _build_and_run_deployment(deployment_id: str):
    deployment = Deployment.objects.select_related("model_version").get(id=deployment_id)

    try:
        with transaction.atomic():
            deployment.transition_to(Deployment.Status.BUILDING)
            deployment.last_error = None
            deployment.build_logs = None
            deployment.save(update_fields=["status", "last_error", "build_logs", "updated_at"])

        build_path = Path(deployment.model_version.artifact_path)
        if not build_path.exists() or not build_path.is_dir():
            raise RuntimeError("Build context directory does not exist")

        image_name, build_logs = container_manager.build_image(
            deployment_id=str(deployment.id),
            build_context_path=str(build_path),
            image_name=f"model-deployment:{deployment.id}",
        )

        container = container_manager.run_container(
            image_name=image_name,
            deployment_id=str(deployment.id),
            network_name="model_network",
            internal_port=5000,
        )

        deployment.refresh_from_db()
        deployment.transition_to(Deployment.Status.RUNNING)
        deployment.image_name = image_name
        deployment.container_name = container.name
        deployment.container_id = container.id
        deployment.internal_url = f"http://{container.name}:5000"
        deployment.endpoint_url = deployment.internal_url
        deployment.build_logs = build_logs[-12000:] if build_logs else None
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
