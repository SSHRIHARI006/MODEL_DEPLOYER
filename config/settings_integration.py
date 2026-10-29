"""Integration test settings — uses real PostgreSQL, Redis, and MinIO.

Run with: DJANGO_SETTINGS_MODULE=config.settings_integration pytest -m integration
"""
from __future__ import annotations

import os

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("TEST_DB_NAME", "model_deployer_test"),
        "USER": os.getenv("TEST_DB_USER", "postgres"),
        "PASSWORD": os.getenv("TEST_DB_PASSWORD", "postgrespassword"),
        "HOST": os.getenv("TEST_DB_HOST", "localhost"),
        "PORT": os.getenv("TEST_DB_PORT", "5432"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("TEST_REDIS_URL", "redis://localhost:6379/2"),
    }
}

CELERY_TASK_ALWAYS_EAGER = True
