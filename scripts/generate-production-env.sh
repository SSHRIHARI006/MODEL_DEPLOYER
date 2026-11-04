#!/usr/bin/env bash
set -euo pipefail

# Generate a production .env from .env.example without printing secrets.
# Usage: ./scripts/generate-production-env.sh modeldeploy.example.com

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <public-domain>" >&2
  exit 2
fi

DOMAIN="$1"
case "$DOMAIN" in
  *[!A-Za-z0-9.-]*|'')
    echo "Invalid domain: $DOMAIN" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TEMPLATE="$REPO_ROOT/.env.example"
OUTPUT="$REPO_ROOT/.env"

if [ ! -f "$TEMPLATE" ]; then
  echo "Missing template: $TEMPLATE" >&2
  exit 1
fi

if [ -e "$OUTPUT" ]; then
  echo "$OUTPUT already exists; refusing to overwrite it." >&2
  echo "Move it aside or remove it only after confirming you have a backup." >&2
  exit 1
fi

TMP_OUTPUT="$(mktemp "$REPO_ROOT/.env.generated.XXXXXX")"
trap 'rm -f "$TMP_OUTPUT"' EXIT

DOMAIN="$DOMAIN" TEMPLATE="$TEMPLATE" OUTPUT="$TMP_OUTPUT" python3 - <<'PY'
import os
import secrets
from pathlib import Path

template = Path(os.environ["TEMPLATE"])
output = Path(os.environ["OUTPUT"])
domain = os.environ["DOMAIN"]

values = {
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
    "DJANGO_DEBUG": "false",
    "DJANGO_ALLOWED_HOSTS": domain,
    "DJANGO_CORS_ALLOWED_ORIGINS": f"https://{domain}",
    "DJANGO_SECURE_SSL_REDIRECT": "true",
    "DJANGO_SECURE_COOKIES": "true",
    "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://{domain}",
    "POSTGRES_PASSWORD": secrets.token_hex(32),
    "MINIO_ROOT_USER": f"mdroot{secrets.token_hex(10)}",
    "MINIO_ROOT_PASSWORD": secrets.token_hex(32),
    "MINIO_WORKER_USER": f"mdrunner{secrets.token_hex(10)}",
    "MINIO_WORKER_PASSWORD": secrets.token_hex(32),
    "REDIS_PASSWORD": secrets.token_hex(32),
    "RUNNER_AUTH_TOKEN": secrets.token_urlsafe(48),
    "UPLOAD_APPROVAL_REQUIRED": "true",
    "BILLING_ENABLED": "false",
    "API_PORT": "8000",
    "FRONTEND_PORT": "8080",
}

redis_password = values["REDIS_PASSWORD"]
values.update(
    REDIS_URL=f"redis://:{redis_password}@redis:6379/0",
    CELERY_BROKER_URL=f"redis://:{redis_password}@redis:6379/1",
    CELERY_RESULT_BACKEND=f"redis://:{redis_password}@redis:6379/1",
)

seen = set()
lines = []
for line in template.read_text(encoding="utf-8").splitlines():
    stripped = line.lstrip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        key = stripped.split("=", 1)[0].strip()
        if key in values:
            lines.append(f"{key}={values[key]}")
            seen.add(key)
            continue
    lines.append(line)

missing = sorted(set(values) - seen)
if missing:
    lines.extend(["", "# Generated production overrides"])
    lines.extend(f"{key}={values[key]}" for key in missing)

output.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

chmod 600 "$TMP_OUTPUT"
mv "$TMP_OUTPUT" "$OUTPUT"
trap - EXIT

if grep -Eq 'replace-with-|dev-insecure-change-me' "$OUTPUT"; then
  echo "Generated .env still contains a placeholder; refusing to continue." >&2
  exit 1
fi

echo "Created $OUTPUT for https://$DOMAIN"
echo "Permissions set to 600. Credentials were not printed."
echo "Review non-secret settings, then run: docker compose config -q"
