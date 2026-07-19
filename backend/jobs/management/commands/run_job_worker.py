import signal
import socket
import time
from uuid import uuid4

from django.core.management.base import BaseCommand

from jobs.worker import claim_next_job, execute_claimed_job, remove_worker, touch_worker


class Command(BaseCommand):
    """Run the durable AW Center background job worker."""

    help = "Claim and execute durable AW Center jobs."

    def add_arguments(self, parser):
        """Register worker polling and one-shot options."""

        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=1.0)

    def handle(self, *args, **options):
        """Poll until stopped, or process at most one job in one-shot mode."""

        self.stopping = False
        self.install_signal_handlers()
        worker_id = f"{socket.gethostname()}:{uuid4().hex[:12]}"
        self.stdout.write(f"Job worker started: {worker_id}")
        try:
            self.run_loop(worker_id, options)
        finally:
            remove_worker(worker_id)

    def run_loop(self, worker_id, options):
        """Poll and execute jobs until shutdown is requested."""

        while not self.stopping:
            touch_worker(worker_id)
            job = claim_next_job(worker_id)
            if job:
                touch_worker(worker_id, job)
                execute_claimed_job(job)
            if options["once"]:
                break
            time.sleep(max(0.1, options["poll_interval"]))

    def install_signal_handlers(self):
        """Request graceful shutdown after the current executor returns."""

        def stop_worker(*_args):
            self.stopping = True

        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)
