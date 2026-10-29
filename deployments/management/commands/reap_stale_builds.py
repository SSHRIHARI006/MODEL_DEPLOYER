from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.runner_errors import RUNNER_CODE_WORKER_TIMEOUT
from deployments.models import Deployment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reap deployments stuck in BUILDING status past a timeout threshold."

    def add_arguments(self, parser):
        parser.add_argument(
            "--threshold-minutes",
            type=int,
            default=30,
            help="Threshold in minutes after which a BUILDING deployment is considered stale (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the reap without updating the database.",
        )

    def handle(self, *args, **options):
        threshold_minutes = options["threshold_minutes"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(minutes=threshold_minutes)

        stale_deployments = Deployment.objects.filter(
            status=Deployment.Status.BUILDING,
            updated_at__lt=cutoff,
        )
        count = stale_deployments.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No stale BUILDING deployments found."))
            return

        self.stdout.write(
            f"Found {count} stale BUILDING deployment(s) older than {threshold_minutes} minutes."
        )

        for dep in stale_deployments:
            if dry_run:
                self.stdout.write(f"[DRY-RUN] Would reap deployment {dep.id}")
            else:
                dep.transition_to(Deployment.Status.FAILED)
                dep.last_error = "reaped: stale BUILDING state"
                dep.last_error_code = RUNNER_CODE_WORKER_TIMEOUT
                dep.save(update_fields=["status", "last_error", "last_error_code", "updated_at"])
                self.stdout.write(self.style.WARNING(f"Reaped stale deployment {dep.id} -> FAILED"))
                logger.warning("Reaped stale deployment %s", dep.id)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed {count} stale deployment(s).")
        )
