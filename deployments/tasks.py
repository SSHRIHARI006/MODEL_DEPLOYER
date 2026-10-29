from __future__ import annotations

import logging
import uuid

from celery import shared_task
from django.conf import settings
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
    init_timeout = getattr(settings, "RUNNER_INIT_TIMEOUT_SECONDS", 300)
    lock_timeout = int(init_timeout) + 60
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

        attempt = (getattr(self.request, "retries", 0) or 0) + 1
        task_id = self.request.id or lock_value
        Deployment.objects.filter(id=deployment_id).update(
            celery_task_id=task_id,
            build_attempt=attempt,
        )

        try:
            _build_and_run_deployment(deployment_id)
        except DeploymentCancelledError:
            return {"status": "stopped", "deployment_id": deployment_id}
        except RetryableDeploymentError as exc:
            code = getattr(exc, "code", "RUNNER_WORKER_TIMEOUT")
            if self.request.retries >= self.max_retries:
                _mark_failed(deployment_id, exc, code=code)
                return {"status": "failed", "deployment_id": deployment_id}
            raise self.retry(exc=exc, countdown=30 * (3**self.request.retries))
        except Exception as exc:
            code = getattr(exc, "code", "RUNNER_INTERNAL")
            _mark_failed(deployment_id, exc, code=code)
            return {"status": "failed", "deployment_id": deployment_id}

        return {"status": "running", "deployment_id": deployment_id}
    finally:
        close_old_connections()
        if cache.get(lock_key) == lock_value:
            cache.delete(lock_key)


def _mark_failed(deployment_id: str, error: Exception, code: str | None = None) -> None:
    try:
        deployment = Deployment.objects.get(id=deployment_id)
    except Deployment.DoesNotExist:
        return
    # Never overwrite a terminal state (e.g. STOPPED or RUNNING) during failure cleanup (REL-06)
    if deployment.status in (Deployment.Status.PENDING, Deployment.Status.BUILDING):
        deployment.transition_to(Deployment.Status.FAILED)
    deployment.last_error = str(error)
    resolved_code = code or getattr(error, "code", None) or "RUNNER_INTERNAL"
    deployment.last_error_code = resolved_code
    deployment.save(
        update_fields=["status", "last_error", "last_error_code", "updated_at"]
    )
