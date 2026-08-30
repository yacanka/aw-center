import signal
import socket
from pathlib import Path
from threading import Event
from uuid import uuid4

from django.core.management.base import BaseCommand

from awcenter.job_executors import (
    local_job_kinds,
    local_job_timeout,
    resolve_job_executor,
)
from jobs.execution import remove_worker, touch_worker
from jobs.worker import claim_next_job, execute_claimed_job


class Command(BaseCommand):
    """Run the durable AW Center background job worker."""

    help = "Claim and execute durable AW Center jobs."

    def add_arguments(self, parser):
        """Register worker polling and one-shot options."""

        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=1.0)
        parser.add_argument("--heartbeat-file")

    def handle(self, *args, **options):
        """Poll until stopped, or process at most one job in one-shot mode."""

        self.stopping = Event()
        self.install_signal_handlers()
        worker_id = f"{socket.gethostname()[:110]}:{uuid4().hex[:12]}"
        heartbeat_file = options["heartbeat_file"]
        if heartbeat_file:
            Path(heartbeat_file).write_text(worker_id, encoding="utf-8")
        self.stdout.write(f"Job worker started: {worker_id}")
        try:
            self.run_loop(worker_id, options)
        finally:
            try:
                remove_worker(worker_id)
            finally:
                if heartbeat_file:
                    Path(heartbeat_file).unlink(missing_ok=True)

    def run_loop(self, worker_id, options):
        """Poll and execute jobs until shutdown is requested."""

        while not self.stopping.is_set():
            touch_worker(worker_id)
            job = claim_next_job(worker_id, local_job_kinds())
            if job:
                execute_claimed_job(
                    job,
                    resolve_job_executor,
                    timeout_seconds=local_job_timeout(job.kind),
                    isolate=True,
                )
            if options["once"]:
                break
            self.stopping.wait(max(0.1, options["poll_interval"]))

    def install_signal_handlers(self):
        """Request graceful shutdown after the current executor returns."""

        def stop_worker(*_args):
            self.stopping.set()

        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)
