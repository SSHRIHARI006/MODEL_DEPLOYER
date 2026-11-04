#!/usr/bin/env bash
set -euo pipefail

# Validate a generated .env and a running Compose deployment without exposing
# credentials. Run from the repository or call it with an absolute path.
# Usage: ./scripts/verify-deployment.sh [--production]

MODE="${1:-local}"
if [ "$MODE" != "local" ] && [ "$MODE" != "--production" ]; then
  echo "Usage: $0 [--production]" >&2
  exit 2
fi

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f .env ]; then
  echo "Missing .env. Generate it first with:" >&2
  echo "  ./scripts/generate-production-env.sh your-domain.example" >&2
  exit 1
fi

required_keys=(
  DJANGO_SECRET_KEY POSTGRES_PASSWORD MINIO_ROOT_USER MINIO_ROOT_PASSWORD
  MINIO_WORKER_USER MINIO_WORKER_PASSWORD REDIS_PASSWORD RUNNER_AUTH_TOKEN
)

for key in "${required_keys[@]}"; do
  if ! grep -Eq "^${key}=.+$" .env; then
    echo "Missing or empty .env value: ${key}" >&2
    exit 1
  fi
done

if grep -Eq 'replace-with-|dev-insecure-change-me' .env; then
  echo "The .env file still contains a placeholder value." >&2
  exit 1
fi

if [ "$MODE" = "--production" ]; then
  for expected in \
    'DJANGO_DEBUG=false' \
    'DJANGO_SECURE_SSL_REDIRECT=true' \
    'DJANGO_SECURE_COOKIES=true' \
    'UPLOAD_APPROVAL_REQUIRED=true'; do
    if ! grep -Fxq "$expected" .env; then
      echo "Production setting missing or incorrect: ${expected}" >&2
      exit 1
    fi
  done
fi

docker compose config -q

echo "Compose configuration: OK"
docker compose exec -T api python manage.py check
docker compose exec -T api python manage.py makemigrations --check --dry-run

docker compose exec -T api python - <<'PY'
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import requests
import django
from django.conf import settings

django.setup()
host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "localhost"
session = requests.Session()
session.trust_env = False
response = session.get(
    "http://127.0.0.1:8000/api/metrics/ready/",
    headers={"Host": host},
    timeout=10,
)
print(f"API readiness: HTTP {response.status_code}")
print(response.text)
if response.status_code != 200:
    raise SystemExit(1)

print(f"Django DEBUG: {settings.DEBUG}")
print(f"Upload approval required: {settings.UPLOAD_APPROVAL_REQUIRED}")
print(f"Billing enabled: {settings.BILLING_ENABLED}")
print(f"Secure SSL redirect: {settings.SECURE_SSL_REDIRECT}")
print(f"Secure cookies: {settings.SESSION_COOKIE_SECURE}")
PY

echo "Deployment verification completed successfully."
