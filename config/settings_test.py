import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-insecure-secret-key")
# SEC-02: the runner credential is required outside development; tests run with
# DJANGO_DEBUG=false, so provide a non-secret test value.
os.environ.setdefault("RUNNER_AUTH_TOKEN", "test-runner-auth-token")
os.environ.setdefault("RUNNER_BASE_URL", "http://localhost:8002")
os.environ.setdefault("RUNNER_INIT_TIMEOUT_SECONDS", "300")
os.environ.setdefault("RUNNER_PREDICT_TIMEOUT_SECONDS", "15")
os.environ.setdefault("RUNNER_HEALTHCHECK_TIMEOUT_SECONDS", "30")
os.environ.setdefault("RUNNER_COMMAND_TIMEOUT_SECONDS", "60")
os.environ.setdefault("RUNNER_MAX_OUTPUT_BYTES", str(128 * 1024))
os.environ.setdefault("RUNNER_MAX_CONCURRENT_BUILDS", "1")
os.environ.setdefault("RUNNER_MAX_CONCURRENT_PREDICTIONS", "8")
os.environ.setdefault("CELERY_TASK_SOFT_TIME_LIMIT", "600")
os.environ.setdefault("CELERY_TASK_TIME_LIMIT", "900")
os.environ.setdefault("CELERY_WORKER_CONCURRENCY", "2")

from .settings import *  # noqa: E402,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# The suite exercises the monetized path by default; tests that cover the
# self-hosted (un-metered) behaviour opt out explicitly.
BILLING_ENABLED = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "model-deployer-tests",
    }
}

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": (),
}

# SEC-07 throttling is enabled by default in every deployment; the suite turns it
# off so tests do not trip over shared anonymous rate limits.
THROTTLING_ENABLED = False
