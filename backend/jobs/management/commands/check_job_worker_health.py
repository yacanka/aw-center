"""Container health contract for the durable job worker pool."""

import json
import os
import signal
from threading import Event
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError, close_old_connections
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from jobs.models import WorkerHeartbeat


class Command(BaseCommand):
    help = "Fail when no durable job worker has published a recent heartbeat."

    def add_arguments(self, parser):
        parser.add_argument("--worker-id-file")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--status-file")

    def handle(self, *args, **options):
        if options['watch']:
            if not options['worker_id_file'] or not options['status_file']:
                raise CommandError('Watch requires worker identity and status files.')
            return self.watch(Path(options['worker_id_file']), Path(options['status_file']))
        self.active_worker(options['worker_id_file'])
        self.stdout.write("Durable job worker heartbeat is active.")

    def active_worker(self, worker_id_file):
        stale_seconds = max(5, int(settings.JOB_WORKER_STALE_SECONDS))
        active_since = timezone.now() - timedelta(seconds=stale_seconds)
        workers = WorkerHeartbeat.objects.filter(heartbeat_at__gte=active_since)
        if worker_id_file:
            try:
                worker_id = Path(worker_id_file).read_text(encoding="utf-8").strip()
            except OSError as error:
                raise CommandError("The worker identity file is unavailable.") from error
            if not worker_id or len(worker_id) > 128:
                raise CommandError("The worker identity file is invalid.")
            workers = workers.filter(worker_id=worker_id)
        worker = workers.order_by('-heartbeat_at').first()
        if worker is None:
            raise CommandError("No durable job worker heartbeat is active.")
        return worker, stale_seconds

    def publish_health(self, identity, status):
        """Publish only a current, identity-bound DB result in the private session."""
        temporary = status.with_suffix('.tmp')
        try:
            worker, stale_seconds = self.active_worker(identity)
            result = {'worker_id': worker.worker_id, 'checked_at': timezone.now().timestamp(),
                      'valid_until': (worker.heartbeat_at + timedelta(seconds=stale_seconds)).timestamp()}
            temporary.write_text(json.dumps(result), encoding='utf-8')
            os.replace(temporary, status)
        except (CommandError, DatabaseError, OSError, UnicodeError):
            discard_status(status)
        finally:
            discard_status(temporary)

    def watch(self, identity, status):
        """Import Django once; supervisor owns this monitor just like its workers."""
        stopped = Event()
        def stop(*_):
            stopped.set()
        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            while not stopped.is_set():
                close_old_connections()
                self.publish_health(identity, status)
                stopped.wait(1)
        finally:
            discard_status(status)
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def discard_status(path):
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        # Windows readers can briefly deny deletion/replacement. The launcher
        # independently expires the previous receipt; retry on the next cycle.
        pass
