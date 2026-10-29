from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def delete_prefix_paginated(
    s3_client: Any,
    bucket: str,
    prefix: str,
    *,
    dry_run: bool = False,
    batch_size: int = 1000,
) -> int:
    """Delete all objects under *prefix* in *bucket*, handling pagination.

    S3 delete_objects API only accepts up to 1000 keys per call. This utility
    paginates through all matching objects and batches the deletions.

    Returns the total number of objects deleted (or that would be deleted in
    dry-run mode).
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    total_deleted = 0
    batch: list[dict[str, str]] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        contents = page.get("Contents", [])
        for obj in contents:
            batch.append({"Key": obj["Key"]})
            if len(batch) >= batch_size:
                if not dry_run:
                    s3_client.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": batch},
                    )
                    logger.info(
                        "Deleted batch of %d objects from s3://%s/%s",
                        len(batch),
                        bucket,
                        prefix,
                    )
                total_deleted += len(batch)
                batch = []

    if batch:
        if not dry_run:
            s3_client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": batch},
            )
            logger.info(
                "Deleted final batch of %d objects from s3://%s/%s",
                len(batch),
                bucket,
                prefix,
            )
        total_deleted += len(batch)

    return total_deleted
