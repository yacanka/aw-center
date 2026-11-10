"""Lease-fenced execution context and heartbeat primitives for job adapters."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from threading import Event, Thread

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models.functions import Now
from django.utils import timezone

from .contracts import JobCancelled, JobLeaseLost
from .models import Job, JobStatus, WorkerHeartbeat
from .services import record_event

logger = logging.getLogger(__name__)

ACTIVE_EXECUTION_STATUSES = (JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED)


@dataclass(frozen=True)
class ExecutionLease:
    """Identify one non-transferable claim of a durable job."""

    job_id: object
    worker_id: str
    token: object

    @classmethod
    def from_job(cls, job):
        """Build a lease from a freshly claimed job instance."""

        if not job.worker_id or not job.execution_token:
            raise JobLeaseLost("The job has no active execution claim.")
        return cls(job.id, job.worker_id, job.execution_token)


_current_lease = ContextVar("job_execution_lease", default=None)


@contextmanager
def bind_execution(job):
    """Bind adapter progress calls to exactly one worker claim."""

    lease = ExecutionLease.from_job(job)
    context_token = _current_lease.set(lease)
    try:
        yield lease
    finally:
        _current_lease.reset(context_token)


def current_execution_lease(job_id):
    """Return the bound claim, rejecting calls from stale or unbound adapters."""

    lease = _current_lease.get()
    if lease is None or str(lease.job_id) != str(job_id):
        raise JobLeaseLost("The execution claim is no longer active.")
    return lease


def update_progress(job_id, progress, message):
    """Publish monotonic progress only while the bound claim still owns the job."""

    lease = current_execution_lease(job_id)
    update_execution_progress(lease, progress, message)


def update_execution_progress(lease, progress, message):
    """Publish fenced progress for an explicit local or remote execution lease."""

    with transaction.atomic():
        job = lock_active_execution(lease)
        job.lease_expires_at = lease_deadline()
        next_progress = max(job.progress, min(99, int(progress)))
        next_message = str(message)[:500]
        changed = next_progress != job.progress or next_message != job.message
        job.progress = next_progress
        job.message = next_message
        job.save(
            update_fields=["progress", "message", "lease_expires_at", "updated_at"]
        )
        touch_worker(lease.worker_id, job)
        if changed:
            record_event(job, job.message)


def cancellation_requested(job_id):
    """Return cancellation intent only if the bound claim remains valid."""

    lease = current_execution_lease(job_id)
    try:
        job = Job.objects.only(
            "status", "worker_id", "execution_token", "lease_expires_at"
        ).get(pk=job_id)
    except Job.DoesNotExist as error:
        raise JobLeaseLost("The execution claim is no longer active.") from error
    validate_active_execution(job, lease, allow_cancel_requested=True)
    return job.status == JobStatus.CANCEL_REQUESTED


def execution_status(lease):
    """Return the current state only while an explicit claim remains live."""

    try:
        job = Job.objects.only(
            "status", "worker_id", "execution_token", "lease_expires_at"
        ).get(pk=lease.job_id)
    except Job.DoesNotExist as error:
        raise JobLeaseLost("The execution claim is no longer active.") from error
    validate_active_execution(job, lease, allow_cancel_requested=True)
    return job.status


def lock_active_execution(lease, *, allow_cancel_requested=False):
    """Lock and return the row only when the supplied claim still owns it."""

    try:
        job = Job.objects.select_for_update().get(pk=lease.job_id)
    except Job.DoesNotExist as error:
        raise JobLeaseLost("The execution claim is no longer active.") from error
    validate_active_execution(job, lease, allow_cancel_requested=allow_cancel_requested)
    return job


def validate_active_execution(job, lease, *, allow_cancel_requested=False):
    """Reject replaced, expired, terminal, or cancellation-fenced claims."""

    token_matches = bool(job.execution_token) and str(job.execution_token) == str(lease.token)
    lease_is_live = bool(job.lease_expires_at) and job.lease_expires_at > timezone.now()
    if (
        job.worker_id != lease.worker_id
        or not token_matches
        or job.status not in ACTIVE_EXECUTION_STATUSES
        or not lease_is_live
    ):
        raise JobLeaseLost("The execution claim is no longer active.")
    if job.status == JobStatus.CANCEL_REQUESTED and not allow_cancel_requested:
        raise JobCancelled()


def renew_execution_lease(lease):
    """CAS-renew one live claim without allowing an expired owner to revive it."""

    with transaction.atomic():
        updated = Job.objects.filter(
            pk=lease.job_id,
            worker_id=lease.worker_id,
            execution_token=lease.token,
            status__in=ACTIVE_EXECUTION_STATUSES,
            lease_expires_at__gt=Now(),
        ).update(lease_expires_at=Now() + lease_duration())
        if updated:
            WorkerHeartbeat.objects.update_or_create(
                worker_id=lease.worker_id,
                defaults={"current_job_id": lease.job_id},
            )
    return bool(updated)


class ExecutionHeartbeat:
    """Renew a claim on a separate DB connection while its adapter is busy."""

    def __init__(self, lease):
        self.lease = lease
        self.interval = heartbeat_interval()
        self._stop = Event()
        self._thread = Thread(
            target=self._run,
            name=f"job-heartbeat-{str(lease.job_id)[:8]}",
            daemon=True,
        )

    def start(self):
        """Verify ownership once before dispatching executor code."""

        if not renew_execution_lease(self.lease):
            raise JobLeaseLost("The execution claim is no longer active.")
        self._thread.start()

    def stop(self):
        """Stop renewal without waiting indefinitely on a database call."""

        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=max(1.0, min(5.0, self.interval * 2)))

    def _run(self):
        close_old_connections()
        try:
            while not self._stop.wait(self.interval):
                if not renew_execution_lease(self.lease):
                    return
        except Exception as error:
            logger.error(
                "Job heartbeat failed",
                extra={
                    "job_id": str(self.lease.job_id),
                    "worker_id": self.lease.worker_id,
                    "error_type": type(error).__name__,
                },
            )
        finally:
            close_old_connections()


def lease_deadline():
    """Return the current worker lease deadline."""

    return timezone.now() + lease_duration()


def lease_duration():
    """Return the configured lease duration with a safe lower bound."""

    seconds = int(getattr(settings, "JOB_LEASE_SECONDS", 60))
    return timedelta(seconds=max(15, seconds))


def heartbeat_interval():
    """Return a bounded interval that remains safely below the lease duration."""

    configured = float(getattr(settings, "JOB_HEARTBEAT_SECONDS", 2))
    lease_seconds = max(15, int(getattr(settings, "JOB_LEASE_SECONDS", 60)))
    return max(0.1, min(configured, lease_seconds / 3))


def touch_worker(worker_id, current_job=None):
    """Publish one durable worker heartbeat for system visibility."""

    if worker_id:
        WorkerHeartbeat.objects.update_or_create(
            worker_id=worker_id, defaults={"current_job": current_job}
        )


def remove_worker(worker_id):
    """Remove a worker heartbeat during graceful shutdown."""

    WorkerHeartbeat.objects.filter(worker_id=worker_id).delete()
