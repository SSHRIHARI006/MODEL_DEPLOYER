#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BACKUP_DIR="${1:-./backups/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$BACKUP_DIR"

DB_NAME="${POSTGRES_DB:-model_deployer}"
DB_USER="${POSTGRES_USER:-ml_user}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
export PGPASSWORD="${POSTGRES_PASSWORD:-postgres123}"

echo "[INFO] Starting database backup to ${BACKUP_DIR}/postgres.dump..."
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -F c -b -f "${BACKUP_DIR}/postgres.dump" "$DB_NAME"

echo "[INFO] Starting MinIO storage backup to ${BACKUP_DIR}/storage.tar.gz..."
.venv/bin/python - "$BACKUP_DIR" "$DB_NAME" <<'PY'
import os
import sys
import tarfile
import tempfile
from pathlib import Path

import boto3
from botocore.client import Config

sys.path.insert(0, str(Path.cwd() / "scripts"))
from restore_helpers import create_manifest, validate_manifest, validate_storage_archive

backup_dir = Path(sys.argv[1])
database = sys.argv[2]
endpoint = os.environ.get("MINIO_ENDPOINT") or os.environ.get("AWS_S3_ENDPOINT_URL", "http://localhost:9000")
key_id = os.environ.get("MINIO_ROOT_USER") or os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
secret = os.environ.get("MINIO_ROOT_PASSWORD") or os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
bucket = os.environ.get("MINIO_BUCKET") or os.environ.get("AWS_STORAGE_BUCKET_NAME", "models")
use_ssl = (os.environ.get("MINIO_USE_SSL") or os.environ.get("AWS_S3_USE_SSL", "false")).lower() == "true"
s3 = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=key_id,
    aws_secret_access_key=secret,
    use_ssl=use_ssl,
    config=Config(s3={"addressing_style": "path"}, connect_timeout=3, retries={"max_attempts": 1}),
)

with tempfile.TemporaryDirectory() as tmpdir:
    root = Path(tmpdir)
    count = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = Path(key)
            if rel.is_absolute() or ".." in rel.parts or "\\" in key:
                raise ValueError(f"unsafe object key: {key!r}")
            local_path = root.joinpath(*rel.parts)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(local_path))
            count += 1

    archive_path = backup_dir / "storage.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(root).as_posix())
    manifest_objects = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )

print(f"Exported {count} storage objects to {backup_dir / 'storage.tar.gz'}")
create_manifest(backup_dir, database, manifest_objects)
validate_manifest(backup_dir)
validate_storage_archive(backup_dir / "storage.tar.gz")
PY

echo "[SUCCESS] Backup completed and checksummed at ${BACKUP_DIR}"
