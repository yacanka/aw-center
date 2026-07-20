"""Create durable jobs that require an explicit owner confirmation."""

from django.db import IntegrityError, transaction

from .models import Job, JobStatus
from .services import (
    calculate_upload_sha256,
    create_job_record,
    find_idempotent_job,
    record_event,
    validate_idempotency_key,
    verify_idempotent_request,
)


def create_confirmation_job(
    owner, kind, title, parameters, uploaded_file, expires_at, summary,
    idempotency_key="", request_id="", source_job=None,
):
    """Persist an immutable job input without exposing it to workers yet."""

    key = validate_idempotency_key(idempotency_key)
    digest = calculate_upload_sha256(uploaded_file)
    existing = find_idempotent_job(owner, kind, key)
    if existing:
        verify_idempotent_request(existing, digest, parameters)
        return existing, False
    job, created = persist_confirmation(
        owner, kind, title, parameters, uploaded_file, digest, key,
        request_id, expires_at, summary, source_job,
    )
    if not created:
        verify_idempotent_request(job, digest, parameters)
        return job, False
    record_event(job, job.message)
    return job, True


def persist_confirmation(
    owner, kind, title, parameters, upload, digest, key,
    request_id, expires_at, summary, source_job,
):
    """Store one pending-confirmation job and clean up partial artifacts."""

    job = None
    try:
        with transaction.atomic():
            job = create_confirmation_record(
                owner, kind, title, parameters, upload, digest, key,
                request_id, expires_at, summary, source_job,
            )
        return job, True
    except IntegrityError:
        if not key:
            raise
        return Job.objects.get(owner=owner, kind=kind, idempotency_key=key), False
    except Exception:
        if job and job.input_file.name:
            job.input_file.storage.delete(job.input_file.name)
        raise


def create_confirmation_record(
    owner, kind, title, parameters, upload, digest, key,
    request_id, expires_at, summary, source_job,
):
    """Create the hidden-from-worker record and its private input atomically."""

    job = create_job_record(
        owner, kind, title, parameters, upload.name, digest, key, request_id,
        source_job,
    )
    job.status = JobStatus.AWAITING_CONFIRMATION
    job.message = "Immutable snapshot ready for confirmation."
    job.confirmation_expires_at = expires_at
    job.result_summary = summary
    job.save()
    job.input_file.save(upload.name, upload, save=True)
    return job
