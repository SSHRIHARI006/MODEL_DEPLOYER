from __future__ import annotations

import logging
import uuid

from celery import shared_task
from django.core.cache import cache
from django.db import close_old_connections

from .models import Deployment
from .services import (
    DeploymentCancelledError,
    RetryableDeploymentError,
    _build_and_run_deployment,
)

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    track_started=True,
)
def build_deployment(self, deployment_id: str):
    lock_key = f"deployment-build:{deployment_id}"
    lock_value = uuid.uuid4().hex
    lock_timeout = 90
    if not cache.add(lock_key, lock_value, timeout=lock_timeout):
        return {"status": "already_running", "deployment_id": deployment_id}

    try:
        close_old_connections()
        try:
            deployment = Deployment.objects.get(id=deployment_id)
        except Deployment.DoesNotExist:
            return {"status": "missing", "deployment_id": deployment_id}

        if deployment.status in (Deployment.Status.RUNNING, Deployment.Status.STOPPED):
            return {"status": deployment.status.lower(), "deployment_id": deployment_id}

        try:
            _build_and_run_deployment(deployment_id)
        except DeploymentCancelledError:
            return {"status": "stopped", "deployment_id": deployment_id}
        except RetryableDeploymentError as exc:
            if self.request.retries >= self.max_retries:
                _mark_failed(deployment_id, exc)
                return {"status": "failed", "deployment_id": deployment_id}
            raise self.retry(exc=exc, countdown=30 * (3**self.request.retries))
        except Exception as exc:
            _mark_failed(deployment_id, exc)
            return {"status": "failed", "deployment_id": deployment_id}

        return {"status": "running", "deployment_id": deployment_id}
    finally:
        close_old_connections()
        if cache.get(lock_key) == lock_value:
            cache.delete(lock_key)


def _mark_failed(deployment_id: str, error: Exception) -> None:
    deployment = Deployment.objects.get(id=deployment_id)
    if deployment.status in (Deployment.Status.PENDING, Deployment.Status.BUILDING):
        deployment.transition_to(Deployment.Status.FAILED)
    deployment.last_error = str(error)
    deployment.save(update_fields=["status", "last_error", "updated_at"])
