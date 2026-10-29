import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models

from model_registry.models import Model

# 32 random bytes -> 64 hex characters of entropy in the raw key.
KEY_BYTES = 32
KEY_PREFIX_LENGTH = 8


def generate_api_key() -> str:
    return secrets.token_hex(KEY_BYTES)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 digest of a raw key. Only the digest is ever stored (SEC-07)."""
    return hashlib.sha256(str(raw_key).encode("utf-8")).hexdigest()


def hashed_key_fields(raw_key: str) -> dict[str, str]:
    """The stored representation of a raw key: digest plus a display prefix."""
    return {
        "key_hash": hash_api_key(raw_key),
        "key_prefix": raw_key[:KEY_PREFIX_LENGTH],
    }


class APIKey(models.Model):
    """Model-specific API key.

    SEC-07: the key is hashed at rest. There is no plaintext column, so a
    database dump cannot be replayed as a credential. The raw value exists only
    on the instance that generated it, long enough to be returned once.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    key_prefix = models.CharField(max_length=12, blank=True, default="")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    model = models.ForeignKey(Model, on_delete=models.CASCADE)

    name = models.CharField(max_length=100, default="default")

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set only for the instance that generated the key; never persisted.
        self.raw_key: str | None = None

    def save(self, *args, **kwargs):
        if not self.key_hash:
            self.raw_key = generate_api_key()
            for field, value in hashed_key_fields(self.raw_key).items():
                setattr(self, field, value)
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
