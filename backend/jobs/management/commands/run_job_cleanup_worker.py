"""Run private job retention as an independently supervised lifecycle."""

import logging
import signal
from pathlib import Path
from threading import Event

from django.core.management.base import BaseCommand, CommandError

from jobs.retention import cleanup_expired_jobs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Periodically apply job retention until the supervisor stops this process."""

    help = "Run periodic durable-job cleanup."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=300.0)
        parser.add_argument("--days", type=int)
        parser.add_argument("--heartbeat-file")

    def handle(self, *args, **options):
        self.stopping = Event()
        self.install_signal_handlers()
        heartbeat_file = options["heartbeat_file"]
        if heartbeat_file:
            Path(heartbeat_file).unlink(missing_ok=True)
        while not self.stopping.is_set():
            succeeded = self.run_cleanup(options["days"], heartbeat_file)
            if options["once"]:
                if not succeeded:
                    raise CommandError("Job cleanup pass failed.")
                return
            self.stopping.wait(max(10.0, options["poll_interval"]))

    def run_cleanup(self, days, heartbeat_file):
        try:
            result = cleanup_expired_jobs(days)
            if heartbeat_file:
                Path(heartbeat_file).touch()
            self.stdout.write(
                "Job cleanup: "
                f"previews={result.expired_previews} deleted={result.deleted_objects}"
            )
            return True
        except ValueError as error:
            raise CommandError(str(error)) from error
        except Exception as error:
            logger.error(
                "Job cleanup pass failed; the worker will retry.",
                extra={"error_type": type(error).__name__},
            )
            self.stderr.write("Job cleanup pass failed; the worker will retry.")
            return False

    def install_signal_handlers(self):
        def stop_worker(*_args):
            self.stopping.set()

        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)
