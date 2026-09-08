import signal
import socket
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path
from threading import Event
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from awcenter.job_executors import (
    local_job_kinds,
    local_job_timeout,
    resolve_job_executor,
    resolve_worker_executor,
    worker_job_kinds,
    worker_job_timeout,
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
        doors_mode = parser.add_mutually_exclusive_group()
        doors_mode.add_argument(
            "--include-doors",
            action="store_true",
            help="Consume the DOORS queue in this Windows user session.",
        )
        doors_mode.add_argument(
            "--include-doors-if-enabled",
            action="store_true",
            help="Consume the DOORS queue when DOORS_ENABLED is true.",
        )

    def handle(self, *args, **options):
        """Poll until stopped, or process at most one job in one-shot mode."""

        self.stopping = Event()
        self.install_signal_handlers()
        include_doors = resolve_include_doors(options)
        options["include_doors"] = include_doors
        validate_doors_worker(include_doors)
        prefix = "doors-worker:" if include_doors else "worker:"
        worker_id = f"{prefix}{socket.gethostname()[:90]}:{uuid4().hex[:12]}"
        heartbeat_file = options["heartbeat_file"]
        if heartbeat_file:
            Path(heartbeat_file).write_text(worker_id, encoding="utf-8")
        self.stdout.write(f"Job worker started: {worker_id}")
        lock = doors_worker_lock() if include_doors else nullcontext()
        try:
            with lock:
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
            include_doors = bool(options.get("include_doors", False))
            kinds = (
                worker_job_kinds(include_doors=True)
                if include_doors
                else local_job_kinds()
            )
            job = claim_next_job(worker_id, kinds)
            if job:
                execute_claimed_job(
                    job,
                    resolve_worker_executor if include_doors else resolve_job_executor,
                    timeout_seconds=(
                        worker_job_timeout(job.kind, include_doors=True)
                        if include_doors
                        else local_job_timeout(job.kind)
                    ),
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


def validate_doors_worker(include_doors):
    """Fail closed unless embedded DOORS execution is explicitly configured."""

    if not include_doors:
        return
    if sys.platform != "win32":
        raise CommandError("Embedded DOORS execution is supported only on Windows.")
    if not settings.DOORS_ENABLED:
        raise CommandError("--include-doors requires DOORS_ENABLED=True.")


def resolve_include_doors(options):
    """Resolve strict production and settings-aware development worker modes."""

    if options.get("include_doors_if_enabled", False):
        return bool(settings.DOORS_ENABLED)
    return bool(options.get("include_doors", False))


@contextmanager
def doors_worker_lock():
    """Allow only one DOORS-capable worker in the Windows user session."""

    import msvcrt

    path = Path(settings.DOORS_WORKER_LOCK_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise CommandError("Another DOORS-capable worker is already running.") from error
        try:
            yield
        finally:
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
