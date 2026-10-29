#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  # Do not print the environment or allow parse errors to mask restore failures.
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BACKUP_DIR="${1:-}"
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
  echo "Usage: $0 <backup_directory>" >&2
  exit 2
fi

BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
DB_NAME="${RESTORE_DB:-${POSTGRES_DB:-model_deployer}}"
DB_USER="${POSTGRES_USER:-ml_user}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
export PGPASSWORD="${POSTGRES_PASSWORD:-postgres123}"

# All read-only validation happens before touching either restore target.
.venv/bin/python scripts/restore_helpers.py validate "$BACKUP_DIR"

if [ "${RESTORE_CONFIRM:-}" != "YES" ]; then
  echo "Restore is destructive. Set RESTORE_CONFIRM=YES after verifying the disposable target." >&2
  exit 2
fi
if [ "${RESTORE_ALLOW_NONLOCAL:-}" != "YES" ] && [[ "$DB_HOST" != "localhost" && "$DB_HOST" != "127.0.0.1" && "$DB_HOST" != "::1" ]]; then
  echo "Refusing non-local database target without RESTORE_ALLOW_NONLOCAL=YES" >&2
  exit 2
fi

storage_archive="$BACKUP_DIR/storage.tar.gz"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
.venv/bin/python scripts/restore_helpers.py extract "$storage_archive" "$tmpdir/objects"

echo "[INFO] Restoring Postgres dump to ${DB_NAME}..."
pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" --clean --if-exists "$BACKUP_DIR/postgres.dump"

.venv/bin/python scripts/restore_helpers.py upload "$tmpdir/objects" "${AWS_STORAGE_BUCKET_NAME:-models}"

echo "[SUCCESS] Database and object storage restore completed for ${DB_NAME}"
