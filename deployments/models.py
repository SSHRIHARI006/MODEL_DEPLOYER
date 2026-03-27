from django.db import models
from model_registry.models import ModelVersion
import uuid


class Deployment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "PENDING"
        BUILDING = "BUILDING", "BUILDING"
        RUNNING = "RUNNING", "RUNNING"
        FAILED = "FAILED", "FAILED"
        STOPPED = "STOPPED", "STOPPED"

    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.BUILDING, Status.FAILED},
        Status.BUILDING: {Status.RUNNING, Status.FAILED},
        Status.RUNNING: {Status.STOPPED},
        Status.STOPPED: set(),
        Status.FAILED: {Status.BUILDING},
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    model_version = models.ForeignKey(ModelVersion, on_delete=models.CASCADE, related_name="deployments")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    endpoint_url = models.TextField(blank=True, null=True)

    runtime_type = models.CharField(
        max_length=20,
        default="container",
    )

    image_name = models.CharField(max_length=255, blank=True, null=True)
    container_name = models.CharField(max_length=255, blank=True, null=True)
    container_id = models.CharField(max_length=128, blank=True, null=True)
    internal_url = models.TextField(blank=True, null=True)

    build_logs = models.TextField(blank=True, null=True)
    last_error = models.TextField(blank=True, null=True)

    started_at = models.DateTimeField(blank=True, null=True)
    stopped_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def transition_to(self, new_status: str):
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(f"Invalid transition: {self.status} -> {new_status}")
        self.status = new_status

    def __str__(self):
        return f"{self.id} - {self.status}"