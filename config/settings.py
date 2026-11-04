"""
Django settings for config project.
"""

import os
from decimal import Decimal
from pathlib import Path
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from runners.auth import check_auth_configuration

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
INSECURE_SECRET_VALUES = {
    "dev-insecure-change-me",
    "change-me",
    "replace-with-a-long-random-secret",
}
if not DEBUG and SECRET_KEY in INSECURE_SECRET_VALUES:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a real secret when DJANGO_DEBUG is false"
    )

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
PREDICTION_CACHE_TTL_SECONDS = int(os.getenv("PREDICTION_CACHE_TTL_SECONDS", "300"))
PREDICTION_CACHE_VERSION = os.getenv("PREDICTION_CACHE_VERSION", "v1")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "EXCEPTION_HANDLER": "core.errors.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "predict": "20/min",
        "auth": "10/min",
        "upload": "10/min",
        "keys": "20/min",
        "deposit": "5/min",
    },
}

# SEC-07: scoped throttling is on by default; turn it off only deliberately
# (the test suite, or a deployment that rate limits in its own reverse proxy).
THROTTLING_ENABLED = os.getenv("THROTTLING_ENABLED", "true").lower() == "true"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
CELERY_TASK_EAGER_PROPAGATES = CELERY_TASK_ALWAYS_EAGER
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

# REL-01/REL-03: worker-side subprocess and concurrency behavior is bounded by
# env-driven caps. The worker process enforces per-action timeouts, process-group
# termination, output caps, and in-process semaphores for concurrent builds and
# predictions.

# Celery task bounds so a worker does not keep modifying a deployment after the
# control plane has given up.
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "600"))
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "900"))
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "2"))

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "AUTH_HEADER_TYPES": ("Bearer",),
    # SEC-07: refresh rotation + revocation. A rotated refresh token invalidates
    # its predecessor, so a leaked token cannot be replayed once the legitimate
    # client refreshes, and logout can revoke a token outright.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# Runtime guardrails
MAX_MODEL_ZIP_BYTES = int(os.getenv("MAX_MODEL_ZIP_BYTES", 50 * 1024 * 1024))  # 50 MB

# SEC-04: uploaded archives are attacker-controlled. These are checked against
# the ZIP metadata before extraction and enforced again while writing bytes.
MAX_MODEL_UNCOMPRESSED_BYTES = int(
    os.getenv("MAX_MODEL_UNCOMPRESSED_BYTES", 200 * 1024 * 1024)
)  # 200 MB
MAX_MODEL_ENTRY_BYTES = int(os.getenv("MAX_MODEL_ENTRY_BYTES", 50 * 1024 * 1024))  # 50 MB
MAX_MODEL_ARCHIVE_ENTRIES = int(os.getenv("MAX_MODEL_ARCHIVE_ENTRIES", 512))
MAX_MODEL_PATH_LENGTH = int(os.getenv("MAX_MODEL_PATH_LENGTH", 200))
# Maximum expansion factor for a single entry; 0 disables the check.
MAX_MODEL_COMPRESSION_RATIO = float(os.getenv("MAX_MODEL_COMPRESSION_RATIO", 100))

# SEC-03: an uploaded model is code this platform installs and executes, so keep
# uploads invite/staff-approved until a per-model sandbox exists. Set to false
# only for a deployment where arbitrary uploads are acceptable.
UPLOAD_APPROVAL_REQUIRED = (
    os.getenv("UPLOAD_APPROVAL_REQUIRED", "true").lower() == "true"
)
INFERENCE_TIMEOUT_SECONDS = int(os.getenv("INFERENCE_TIMEOUT_SECONDS", 15))

# REL-01: separate timeouts for runner actions. No single timeout is reused for
# init, predict, health, and command paths anymore.
RUNNER_BASE_URL = os.getenv("RUNNER_BASE_URL", "http://localhost:8002")
RUNNER_INIT_TIMEOUT_SECONDS = int(os.getenv("RUNNER_INIT_TIMEOUT_SECONDS", "300"))
RUNNER_PREDICT_TIMEOUT_SECONDS = int(os.getenv("RUNNER_PREDICT_TIMEOUT_SECONDS", "15"))
RUNNER_HEALTHCHECK_TIMEOUT_SECONDS = int(os.getenv("RUNNER_HEALTHCHECK_TIMEOUT_SECONDS", "30"))
RUNNER_COMMAND_TIMEOUT_SECONDS = int(os.getenv("RUNNER_COMMAND_TIMEOUT_SECONDS", "60"))
RUNNER_MAX_OUTPUT_BYTES = int(os.getenv("RUNNER_MAX_OUTPUT_BYTES", str(128 * 1024)))
RUNNER_MAX_CONCURRENT_BUILDS = int(os.getenv("RUNNER_MAX_CONCURRENT_BUILDS", "1"))
RUNNER_MAX_CONCURRENT_PREDICTIONS = int(os.getenv("RUNNER_MAX_CONCURRENT_PREDICTIONS", "8"))

# Legacy runner URL settings are retained for a transition window only.
RUNNER_SKLEARN_URL = os.getenv("RUNNER_SKLEARN_URL", "http://localhost:8002")
RUNNER_PYTORCH_URL = os.getenv("RUNNER_PYTORCH_URL", "http://localhost:8002")

# Internal runner authentication (SEC-02). The same shared secret is configured
# on the API/Celery containers and on the runner container; the runner refuses
# to start without it. Fail closed here too, so a non-development deployment
# cannot boot with the internal endpoints effectively unprotected.
RUNNER_AUTH_TOKEN = os.getenv("RUNNER_AUTH_TOKEN", "").strip()
RUNNER_AUTH_HEADER = os.getenv("RUNNER_AUTH_HEADER", "X-Runner-Token")
RUNNER_ALLOW_UNAUTHENTICATED = (
    os.getenv("RUNNER_ALLOW_UNAUTHENTICATED", "false").lower() == "true"
)
check_auth_configuration(
    token=RUNNER_AUTH_TOKEN,
    debug=DEBUG,
    allow_unauthenticated=RUNNER_ALLOW_UNAUTHENTICATED,
    service="Django control plane",
)

# Billing (simplified credit system — no real money anywhere)
BILLING_ENABLED = os.getenv("BILLING_ENABLED", "false").lower() == "true"
BILLING_STARTING_CREDITS = Decimal(os.getenv("BILLING_STARTING_CREDITS", "100"))

# SEC-05: deposits mint simulated credits, so they are off unless explicitly
# enabled, and even then restricted to staff (or a DEBUG deployment).
BILLING_DEMO_DEPOSITS = (
    os.getenv("BILLING_DEMO_DEPOSITS", "false").lower() == "true"
)
BILLING_MAX_DEPOSIT_AMOUNT = Decimal(
    os.getenv("BILLING_MAX_DEPOSIT_AMOUNT", "10000")
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "users",
    "api_keys",
    "model_registry",
    "deployments",
    "prediction_gateway",
    "monitoring",
    "billing",
    "authentication",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

USE_SQLITE = os.getenv("DJANGO_USE_SQLITE", "false").lower() == "true"
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

if USE_SQLITE or not POSTGRES_PASSWORD:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "model_deployer"),
            "USER": os.getenv("POSTGRES_USER", "ml_user"),
            "PASSWORD": POSTGRES_PASSWORD,
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
AUTH_USER_MODEL = "users.User"

# CORS — env-driven so the deployed frontend origin can be added per environment
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# TLS terminates at the reverse proxy in production. The proxy emits
# X-Forwarded-Proto, and the deployment can opt into redirects and secure
# cookies without breaking local HTTP development.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_COOKIES = os.getenv("DJANGO_SECURE_COOKIES", "false").lower() == "true"
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s method=%(method)s path=%(path)s status=%(status_code)s duration_ms=%(duration_ms)s message=%(message)s",
        },
        "simple": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "request_console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "request_logger": {
            "handlers": ["request_console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Object Storage (MinIO S3) Settings
AWS_ACCESS_KEY_ID = os.getenv("MINIO_ROOT_USER", "")
AWS_SECRET_ACCESS_KEY = os.getenv("MINIO_ROOT_PASSWORD", "")
AWS_S3_ENDPOINT_URL = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
AWS_STORAGE_BUCKET_NAME = os.getenv("MINIO_BUCKET", "model-artifacts")
AWS_S3_USE_SSL = os.getenv("MINIO_USE_SSL", "false").lower() == "true"
AWS_DEFAULT_ACL = None
