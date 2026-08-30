import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Job, JobStatus
from .persistence import (
    IdempotencyConflict,
    calculate_upload_sha256,
    create_job,
    create_job_record,
    find_idempotent_job,
    persist_job,
    record_event,
    require_idempotency_key,
    validate_idempotency_key,
    verify_idempotent_request,
)

TERMINAL_STATUSES = {
    JobStatus.CANCELLED,
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.RECONCILIATION_REQUIRED,
}
logger = logging.getLogger(__name__)


def request_cancellation(job):
    """Cancel a queued job or request cooperative cancellation for a running job."""

    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.pk)
        if locked.status == JobStatus.QUEUED:
            set_job_state(locked, JobStatus.CANCELLED, locked.progress, "Cancelled before execution.")
        elif locked.status == JobStatus.RUNNING:
            locked.cancel_requested_at = timezone.now()
            set_job_state(locked, JobStatus.CANCEL_REQUESTED, locked.progress, "Cancellation requested.")
        elif locked.status == JobStatus.CANCEL_REQUESTED:
            pass
        elif locked.status not in TERMINAL_STATUSES:
            raise ValidationError({"status": "Job cannot be cancelled from its current state."})
        return locked


def set_job_state(job, status, progress, message, code=""):
    """Persist a bounded job state and append its audit event."""

    worker_id = job.worker_id
    execution_id = str(job.execution_token or "")
    job.status = status
    job.progress = max(0, min(100, int(progress)))
    job.message = str(message)[:500]
    job.error_code = str(code)[:64]
    if status not in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
        job.execution_token = None
    if status in {JobStatus.AWAITING_CONFIRMATION, JobStatus.QUEUED}:
        job.lease_expires_at = None
        job.worker_id = ""
    if status in TERMINAL_STATUSES:
        job.completed_at = timezone.now()
        job.lease_expires_at = None
        job.worker_id = ""
    job.save()
    record_event(job, job.message, code)
    if status in TERMINAL_STATUSES:
        duration_ms = None
        if job.started_at and job.completed_at:
            duration_ms = max(
                0,
                round((job.completed_at - job.started_at).total_seconds() * 1000),
            )
        logger.info(
            "Job reached a terminal state",
            extra={
                "event": "job_terminal",
                "job_id": str(job.id),
                "job_kind": job.kind,
                "attempt": job.attempt,
                "terminal_code": job.error_code or status,
                "worker_id": worker_id,
                "execution_id": execution_id,
                "duration_ms": duration_ms,
                "request_id": job.request_id or "-",
            },
        )
    notify_workflow(job)


def notify_workflow(job):
    """Synchronize an attached workflow without weakening job completion."""

    if not job.workflow_run_id:
        return
    from .workflow_services import synchronize_workflow_job

    synchronize_workflow_job(job)
