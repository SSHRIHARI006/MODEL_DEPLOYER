from django.db import models
from django.conf import settings
from model_registry.models import Model
from deployments.models import Deployment
import uuid

class PredictionLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    uid = models.CharField(max_length=100)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    model = models.ForeignKey(Model, on_delete=models.CASCADE)

    deployment = models.ForeignKey(Deployment, on_delete=models.SET_NULL, null=True)

    input_data = models.JSONField()
    output_data = models.JSONField(blank=True, null=True)

    latency_ms = models.FloatField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("SUCCESS", "SUCCESS"),
            ("ERROR", "ERROR"),
        ],
        default="SUCCESS"
    )

    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.model.name} - {self.status}"