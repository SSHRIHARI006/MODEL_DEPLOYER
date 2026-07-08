"""
Django settings for config project.
"""

import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "predict": "20/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Runtime guardrails
MAX_MODEL_ZIP_BYTES = int(os.getenv("MAX_MODEL_ZIP_BYTES", 50 * 1024 * 1024))  # 50 MB
INFERENCE_TIMEOUT_SECONDS = int(os.getenv("INFERENCE_TIMEOUT_SECONDS", 15))
RUNNER_SKLEARN_URL = os.getenv("RUNNER_SKLEARN_URL", "http://runner-sklearn:8000")
RUNNER_PYTORCH_URL = os.getenv("RUNNER_PYTORCH_URL", "http://runner-pytorch:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
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

STATIC_URL = "static/"
AUTH_USER_MODEL = "users.User"

# CORS — allow the React dev server
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
CORS_ALLOW_CREDENTIALS = True

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
AWS_ACCESS_KEY_ID = os.getenv("MINIO_ROOT_USER", "admin")
AWS_SECRET_ACCESS_KEY = os.getenv("MINIO_ROOT_PASSWORD", "adminpassword")
AWS_S3_ENDPOINT_URL = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
AWS_STORAGE_BUCKET_NAME = os.getenv("MINIO_BUCKET", "model-artifacts")
AWS_S3_USE_SSL = False
AWS_DEFAULT_ACL = "public-read"
