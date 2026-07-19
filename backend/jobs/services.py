import hashlib
import re

from django.core.files import File
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import Job, JobEvent, JobStatus

IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
TERMINAL_STATUSES = {JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED}


class IdempotencyConflict(APIException):
    """Reject reuse of one idempotency key for a different operation."""

    status_code = 409
    default_code = "IDEMPOTENCY_CONFLICT"
    default_detail = "The idempotency key was already used with different input."


def create_job(owner, kind, title, parameters, uploaded_file, idempotency_key="", request_id=""):
    """Create an owned durable job and persist its validated input."""

    normalized_key = validate_idempotency_key(idempotency_key)
    digest = calculate_upload_sha256(uploaded_file)
    existing = find_idempotent_job(owner, kind, normalized_key)
    if existing:
        verify_idempotent_request(existing, digest, parameters)
        return existing, False
    job, created = persist_job(
        owner, kind, title, parameters, uploaded_file, digest, normalized_key, request_id
    )
    if not created:
        verify_idempotent_request(job, digest, parameters)
        return job, False
    record_event(job, "Job queued.")
    return job, True


def persist_job(owner, kind, title, parameters, upload, digest, key, request_id):
    """Persist job metadata and its input artifact."""

    job = None
    try:
        with transaction.atomic():
            job = create_job_record(
                owner, kind, title, parameters, upload.name, digest, key, request_id
            )
            job.input_file.save(upload.name, upload, save=True)
        return job, True
    except IntegrityError:
        if not key:
            raise
        return Job.objects.get(owner=owner, kind=kind, idempotency_key=key), False
    except Exception:
        if job and job.input_file.name:
            job.input_file.storage.delete(job.input_file.name)
        raise


def create_job_record(owner, kind, title, parameters, input_name, digest, key, request_id):
    """Create one job metadata row before its input artifact is committed."""

    return Job.objects.create(
        owner=owner,
        kind=kind,
        title=title,
        parameters=parameters,
        input_name=input_name,
        input_sha256=digest,
        idempotency_key=key,
        request_id=request_id,
    )


def request_cancellation(job):
    """Cancel a queued job or request cooperative cancellation for a running job."""

    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.pk)
        if locked.status == JobStatus.QUEUED:
            set_job_state(locked, JobStatus.CANCELLED, locked.progress, "Cancelled before execution.")
        elif locked.status == JobStatus.RUNNING:
            locked.cancel_requested_at = timezone.now()
            set_job_state(locked, JobStatus.CANCEL_REQUESTED, locked.progress, "Cancellation requested.")
        elif locked.status not in TERMINAL_STATUSES:
            raise ValidationError({"status": "Job cannot be cancelled from its current state."})
        return locked


def retry_job(job):
    """Create a new queued attempt with a copied immutable input artifact."""

    if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        raise ValidationError({"status": "Only failed or cancelled jobs can be retried."})
    if not job.retryable:
        raise ValidationError({"status": "This failure requires corrected input instead of retry."})
    if job.attempt >= job.max_attempts:
        raise ValidationError({"attempt": "Maximum retry count has been reached."})
    retried = clone_job(job)
    record_event(retried, f"Retry queued from attempt {job.attempt}.")
    return retried


def clone_job(job):
    """Copy retry-safe metadata and stream the original input into a new job."""

    clone = Job.objects.create(
        owner=job.owner, kind=job.kind, title=job.title, parameters=job.parameters,
        input_name=job.input_name, input_sha256=job.input_sha256,
        result_summary={},
        retryable=True,
        attempt=job.attempt + 1, max_attempts=job.max_attempts,
        retry_of=job, request_id=job.request_id,
    )
    try:
        with job.input_file.open("rb") as source:
            clone.input_file.save(job.input_name, File(source), save=True)
    except Exception:
        clone.delete()
        raise
    return clone


def set_job_state(job, status, progress, message, code=""):
    """Persist a bounded job state and append its audit event."""

    job.status = status
    job.progress = max(0, min(100, int(progress)))
    job.message = str(message)[:500]
    job.error_code = str(code)[:64]
    if status in TERMINAL_STATUSES:
        job.completed_at = timezone.now()
        job.lease_expires_at = None
        job.worker_id = ""
    job.save()
    record_event(job, job.message, code)


def record_event(job, message, code="", details=None):
    """Append one sanitized immutable event for a job."""

    return JobEvent.objects.create(
        job=job, status=job.status, progress=job.progress,
        message=str(message)[:500], code=str(code)[:64], details=details or {},
    )


def calculate_upload_sha256(uploaded_file):
    """Calculate a streaming SHA-256 digest without retaining upload bytes."""

    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def validate_idempotency_key(value):
    """Validate an optional caller-provided idempotency key."""

    normalized = str(value or "").strip()
    if normalized and not IDEMPOTENCY_PATTERN.fullmatch(normalized):
        raise ValidationError({"idempotency_key": "Use 8-128 safe ASCII characters."})
    return normalized


def find_idempotent_job(owner, kind, key):
    """Return an existing idempotent request when one is available."""

    if not key:
        return None
    return Job.objects.filter(owner=owner, kind=kind, idempotency_key=key).first()


def verify_idempotent_request(job, digest, parameters):
    """Ensure an idempotency replay represents exactly the original request."""

    if job.input_sha256 != digest or job.parameters != parameters:
        raise IdempotencyConflict()
