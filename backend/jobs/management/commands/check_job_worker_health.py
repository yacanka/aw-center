"""Container health contract for the durable job worker pool."""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from jobs.models import WorkerHeartbeat


class Command(BaseCommand):
    help = "Fail when no durable job worker has published a recent heartbeat."

    def add_arguments(self, parser):
        parser.add_argument("--worker-id-file")

    def handle(self, *args, **options):
        stale_seconds = max(5, int(settings.JOB_WORKER_STALE_SECONDS))
        active_since = timezone.now() - timedelta(seconds=stale_seconds)
        workers = WorkerHeartbeat.objects.filter(heartbeat_at__gte=active_since)
        worker_id_file = options["worker_id_file"]
        if worker_id_file:
            try:
                worker_id = Path(worker_id_file).read_text(encoding="utf-8").strip()
            except OSError as error:
                raise CommandError("The worker identity file is unavailable.") from error
            if not worker_id or len(worker_id) > 128:
                raise CommandError("The worker identity file is invalid.")
            workers = workers.filter(worker_id=worker_id)
        if not workers.exists():
            raise CommandError("No durable job worker heartbeat is active.")
        self.stdout.write("Durable job worker heartbeat is active.")
