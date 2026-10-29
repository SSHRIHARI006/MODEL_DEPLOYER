from __future__ import annotations

import logging
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand

from core.storage import delete_prefix_paginated
from model_registry.models import Model, ModelVersion
from model_registry.views import get_s3_client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcile orphaned S3 artifact prefixes and database records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Dry run mode (default: True). Set --delete to actually perform cleanup.",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Actually delete orphaned S3 objects.",
        )

    def handle(self, *args, **options):
        actually_delete = options["delete"]
        dry_run = not actually_delete
        s3_client = get_s3_client()
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        self.stdout.write(f"Scanning bucket s3://{bucket_name} for orphaned artifacts...")

        # 1. Collect all top-level prefixes in S3 (model_id/...)
        paginator = s3_client.get_paginator("list_objects_v2")
        s3_prefixes = set()
        for page in paginator.paginate(Bucket=bucket_name, Delimiter="/"):
            for prefix_info in page.get("CommonPrefixes", []):
                prefix = prefix_info.get("Prefix", "").strip("/")
                if prefix:
                    s3_prefixes.add(prefix)

        self.stdout.write(f"Found {len(s3_prefixes)} prefix(es) in S3.")

        # 2. Check each prefix against database Models
        orphaned_s3_prefixes: list[str] = []
        for prefix in sorted(s3_prefixes):
            # Model IDs are typically UUIDs or string IDs matching the prefix
            if not Model.objects.filter(id=prefix).exists():
                orphaned_s3_prefixes.append(prefix)

        self.stdout.write(
            f"Found {len(orphaned_s3_prefixes)} orphaned S3 prefix(es) with no database record."
        )

        for prefix in orphaned_s3_prefixes:
            full_prefix = f"{prefix}/"
            if dry_run:
                self.stdout.write(f"[DRY-RUN] Would delete s3://{bucket_name}/{full_prefix}")
            else:
                deleted_count = delete_prefix_paginated(
                    s3_client, bucket_name, full_prefix
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"Deleted {deleted_count} object(s) under s3://{bucket_name}/{full_prefix}"
                    )
                )

        # 3. Check database ModelVersions for missing S3 objects
        orphaned_db_versions: list[ModelVersion] = []
        for mv in ModelVersion.objects.all():
            if mv.artifact_path.startswith("s3://"):
                parsed = urlparse(mv.artifact_path)
                s3_key = parsed.path.lstrip("/")
                res = s3_client.list_objects_v2(
                    Bucket=parsed.netloc, Prefix=s3_key, MaxKeys=1
                )
                if not res.get("Contents"):
                    orphaned_db_versions.append(mv)

        self.stdout.write(
            f"Found {len(orphaned_db_versions)} DB ModelVersion(s) with missing S3 artifacts."
        )
        for mv in orphaned_db_versions:
            self.stdout.write(
                self.style.NOTICE(
                    f"DB record missing remote artifact: ModelVersion {mv.id} ({mv.artifact_path})"
                )
            )

        mode_str = "Completed real cleanup" if actually_delete else "Completed dry-run inspection"
        self.stdout.write(self.style.SUCCESS(f"{mode_str}."))
