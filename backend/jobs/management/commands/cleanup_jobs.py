from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import Job, JobStatus


class Command(BaseCommand):
    """Delete expired terminal jobs and their private artifacts."""

    help = "Delete completed job records and artifacts after the retention period."

    def add_arguments(self, parser):
        """Register an optional retention override."""

        parser.add_argument("--days", type=int)

    def handle(self, *args, **options):
        """Delete terminal jobs older than the configured retention window."""

        configured = options["days"]
        days = configured if configured is not None else settings.JOB_ARTIFACT_RETENTION_DAYS
        if days < 1:
            raise ValueError("Retention days must be at least one.")
        cutoff = timezone.now() - timedelta(days=days)
        statuses = [JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED]
        deleted, _ = Job.objects.filter(status__in=statuses, completed_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} expired job records and related events.")
