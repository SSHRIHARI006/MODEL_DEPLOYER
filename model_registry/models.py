from django.db import models
from django.conf import settings
import uuid

class Model(models.Model):
    id = models.CharField(primary_key=True, max_length=50, default=uuid.uuid4)

    name = models.CharField(max_length=255)

    framework = models.CharField(max_length=50)
    task_type = models.CharField(max_length=50)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="models")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ModelVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    model = models.ForeignKey(Model, on_delete=models.CASCADE, related_name="versions")

    version = models.CharField(max_length=20)

    artifact_path = models.TextField()
    schema_path = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("READY", "READY"),
            ("FAILED", "FAILED"),
        ],
        default="READY"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.model.name} - {self.version}"