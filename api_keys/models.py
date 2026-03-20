import uuid
import secrets
from django.db import models
from django.conf import settings
from model_registry.models import Model


def generate_api_key():
    return secrets.token_hex(32)


class APIKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    key = models.CharField(max_length=64, unique=True, blank=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    model = models.ForeignKey(Model, on_delete=models.CASCADE)

    name = models.CharField(max_length=100, default="default")

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = generate_api_key()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.model.name}"