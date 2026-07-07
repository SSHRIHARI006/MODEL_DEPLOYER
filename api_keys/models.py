import uuid
import secrets
import hashlib
from django.db import models
from django.conf import settings
from model_registry.models import Model


def generate_api_key():
    return secrets.token_hex(32)


class APIKey(models.Model):
    """Legacy model-specific API key (preserved for backward compatibility)."""

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


class UniversalAPIKey(models.Model):
    """User-level universal API key for the public compute marketplace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="universal_api_keys",
    )
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=12)  # e.g. md_live_a1b2
    hashed_key = models.CharField(max_length=128, unique=True, db_index=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def generate():
        """Generate a raw key and its prefix + hash. Returns (raw_key, prefix, hashed)."""
        raw = f"md_live_{secrets.token_hex(24)}"
        prefix = raw[:12]
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        return raw, prefix, hashed

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

