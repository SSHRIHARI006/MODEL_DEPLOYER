from django.db import models
from model_registry.models import ModelVersion
import uuid

class Deployment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    model_version = models.ForeignKey(ModelVersion, on_delete=models.CASCADE, related_name="deployments")

    status = models.CharField(
        max_length=20,
        choices=[
            ("DEPLOYING", "DEPLOYING"),
            ("RUNNING", "RUNNING"),
            ("FAILED", "FAILED"),
            ("STOPPED", "STOPPED"),
        ],
        default="DEPLOYING"
    )

    endpoint_url = models.TextField(blank=True, null=True)

    runtime_type = models.CharField(
        max_length=20,
        default="in_memory"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.model_version} - {self.status}"