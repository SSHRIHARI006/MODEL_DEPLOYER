from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models

from deployments.models import Deployment
from model_registry.models import Model


class PredictionLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    uid = models.CharField(max_length=100, default=uuid.uuid4, db_index=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    model = models.ForeignKey(Model, on_delete=models.CASCADE)

    deployment = models.ForeignKey(Deployment, on_delete=models.SET_NULL, null=True)

    input_data = models.JSONField()
    output_data = models.JSONField(blank=True, null=True)

    # Historical overall latency field
    latency_ms = models.FloatField(blank=True, null=True)

    # OBS-01: Split latency fields and explicit cache telemetry
    cache_hit = models.BooleanField(default=False, db_index=True)
    gateway_latency_ms = models.FloatField(blank=True, null=True)
    runner_compute_ms = models.FloatField(blank=True, null=True)
    init_ms = models.FloatField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("SUCCESS", "SUCCESS"),
            ("ERROR", "ERROR"),
        ],
        default="SUCCESS",
    )

    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["model", "created_at"]),
            models.Index(fields=["cache_hit"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.model.name} - {self.status}"
