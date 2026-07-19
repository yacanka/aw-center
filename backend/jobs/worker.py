import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from .contracts import JobCancelled, JobExecutionFailure
from .models import Job, JobStatus, WorkerHeartbeat
from .services import record_event, set_job_state

logger = logging.getLogger(__name__)


def claim_next_job(worker_id):
    """Atomically lease the oldest queued job to one worker."""

    recover_expired_jobs()
    with transaction.atomic():
        job = Job.objects.select_for_update().filter(status=JobStatus.QUEUED).order_by("created_at").first()
        if not job:
            return None
        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or timezone.now()
        job.worker_id = worker_id
        job.lease_expires_at = lease_deadline()
        job.message = "Worker started the job."
        job.save()
        record_event(job, job.message)
        return job


def execute_claimed_job(job):
    """Dispatch one claimed job and persist its terminal state."""

    result = None
    try:
        executor = get_executor(job.kind)
        result = executor(job)
        if cancellation_requested(job.id):
            raise JobCancelled()
        persist_result(job.id, result)
    except JobCancelled:
        mark_cancelled(job.id)
    except JobExecutionFailure as error:
        mark_failed(job.id, str(error), error.code, error.retryable)
    except Exception:
        logger.exception("Unhandled job failure", extra={"job_id": str(job.id)})
        mark_failed(job.id, "The worker could not complete this job.", "JOB_EXECUTION_FAILED", True)
    finally:
        if result and result.path.exists():
            result.path.unlink(missing_ok=True)


def get_executor(kind):
    """Resolve an allowlisted executor without dynamic imports from user data."""

    from excel.cover_pages import execute_cover_page_creation
    from media_tools.job_executor import execute_media_conversion
    from word.job_executor import execute_word_translation
    from word.analysis import execute_document_analysis
    executors = {
        "excel.cover_pages": execute_cover_page_creation,
        "media.convert": execute_media_conversion,
        "word.translate": execute_word_translation,
        "word.analyze": execute_document_analysis,
    }
    if kind not in executors:
        raise JobExecutionFailure("No worker supports this job type.", "JOB_KIND_UNSUPPORTED")
    return executors[kind]


def update_progress(job_id, progress, message):
    """Update progress and renew the worker lease."""

    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if job.status == JobStatus.CANCEL_REQUESTED:
            raise JobCancelled()
        job.lease_expires_at = lease_deadline()
        next_progress = max(job.progress, min(99, int(progress)))
        next_message = str(message)[:500]
        changed = next_progress != job.progress or next_message != job.message
        job.progress = next_progress
        job.message = next_message
        job.save()
        touch_worker(job.worker_id, job)
        if changed:
            record_event(job, job.message)


def cancellation_requested(job_id):
    """Return whether cooperative cancellation was requested."""

    return Job.objects.filter(pk=job_id, status=JobStatus.CANCEL_REQUESTED).exists()


def persist_result(job_id, result):
    """Stream an executor artifact into owned storage and complete the job."""

    job = Job.objects.get(pk=job_id)
    try:
        validate_result_artifact(result.path)
        with result.path.open("rb") as source:
            job.output_sha256 = file_digest(source)
            source.seek(0)
            job.output_file.save(result.filename, File(source), save=False)
        job.output_name = result.filename
        job.result_summary = result.summary or {}
        set_job_state(job, JobStatus.SUCCEEDED, 100, result.message)
    finally:
        result.path.unlink(missing_ok=True)


def validate_result_artifact(path):
    """Reject absent, empty, or oversized executor output."""

    size = path.stat().st_size if path.exists() else 0
    if size == 0:
        raise JobExecutionFailure("The executor produced no output.", "JOB_OUTPUT_MISSING")
    if size > settings.JOB_MAX_OUTPUT_BYTES:
        raise JobExecutionFailure("Generated output exceeds the safety limit.", "JOB_OUTPUT_TOO_LARGE")


def mark_cancelled(job_id):
    """Persist a cooperative cancellation terminal state."""

    job = Job.objects.get(pk=job_id)
    set_job_state(job, JobStatus.CANCELLED, job.progress, "Job cancelled.", "JOB_CANCELLED")


def mark_failed(job_id, message, code, retryable=False):
    """Persist a sanitized terminal failure."""

    job = Job.objects.get(pk=job_id)
    job.retryable = retryable
    set_job_state(job, JobStatus.FAILED, job.progress, message, code)


def recover_expired_jobs():
    """Requeue jobs abandoned after a worker lease expired."""

    statuses = [JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED]
    job_ids = Job.objects.filter(status__in=statuses, lease_expires_at__lt=timezone.now()).values_list("id", flat=True)[:100]
    for job_id in list(job_ids):
        recover_expired_job(job_id)


def recover_expired_job(job_id):
    """Recover one expired lease under a row lock."""

    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if not job.lease_expires_at or job.lease_expires_at >= timezone.now():
            return
        if job.status == JobStatus.CANCEL_REQUESTED:
            set_job_state(job, JobStatus.CANCELLED, job.progress, "Job cancelled.", "JOB_CANCELLED")
        elif job.attempt >= job.max_attempts:
            set_job_state(job, JobStatus.FAILED, job.progress, "Worker lease expired.", "JOB_LEASE_EXPIRED")
        else:
            job.attempt += 1
            job.lease_expires_at = None
            job.worker_id = ""
            set_job_state(job, JobStatus.QUEUED, job.progress, "Recovered after worker interruption.")


def lease_deadline():
    """Return the current worker lease deadline."""

    seconds = int(getattr(settings, "JOB_LEASE_SECONDS", 60))
    return timezone.now() + timedelta(seconds=max(15, seconds))


def file_digest(file_object):
    """Calculate a streaming SHA-256 digest for a generated artifact."""

    digest = hashlib.sha256()
    for chunk in iter(lambda: file_object.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def touch_worker(worker_id, current_job=None):
    """Publish one durable worker heartbeat for system visibility."""

    if worker_id:
        WorkerHeartbeat.objects.update_or_create(
            worker_id=worker_id, defaults={"current_job": current_job}
        )


def remove_worker(worker_id):
    """Remove a worker heartbeat during graceful shutdown."""

    WorkerHeartbeat.objects.filter(worker_id=worker_id).delete()
