import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q

from .storage import private_job_storage


class JobStatus(models.TextChoices):
    AWAITING_CONFIRMATION = "awaiting_confirmation", "Awaiting confirmation"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    CANCEL_REQUESTED = "cancel_requested", "Cancel requested"
    CANCELLED = "cancelled", "Cancelled"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


def job_input_path(instance, filename):
    """Return an opaque owner-scoped storage path for job input."""

    suffix = Path(filename).suffix.lower()
    return f"jobs/{instance.owner_id}/{instance.id}/input{suffix}"


def job_output_path(instance, filename):
    """Return an opaque owner-scoped storage path for job output."""

    suffix = Path(filename).suffix.lower()
    return f"jobs/{instance.owner_id}/{instance.id}/output{suffix}"


class Job(models.Model):
    """Represent one durable, owned background operation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs")
    kind = models.CharField(max_length=64)
    title = models.CharField(max_length=160)
    status = models.CharField(max_length=24, choices=JobStatus.choices, default=JobStatus.QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=500, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    input_file = models.FileField(storage=private_job_storage, upload_to=job_input_path, max_length=500)
    input_name = models.CharField(max_length=180)
    input_sha256 = models.CharField(max_length=64)
    output_file = models.FileField(
        storage=private_job_storage, upload_to=job_output_path, max_length=500, blank=True
    )
    output_name = models.CharField(max_length=180, blank=True)
    output_sha256 = models.CharField(max_length=64, blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    retryable = models.BooleanField(default=True)
    idempotency_key = models.CharField(max_length=128, blank=True)
    attempt = models.PositiveSmallIntegerField(default=1)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    retry_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="retry_attempts"
    )
    source_job = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="handoff_jobs"
    )
    workflow_run = models.ForeignKey(
        "jobs.WorkflowRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs"
    )
    workflow_step = models.PositiveSmallIntegerField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    worker_id = models.CharField(max_length=128, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    confirmation_expires_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["owner", "updated_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "kind", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="jobs_unique_owner_kind_idempotency",
            ),
            models.UniqueConstraint(
                fields=["retry_of"],
                condition=Q(retry_of__isnull=False),
                name="jobs_unique_direct_retry",
            ),
        ]


class JobEvent(models.Model):
    """Record an immutable, sanitized job state event."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=24, choices=JobStatus.choices)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=500, blank=True)
    code = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class WorkerHeartbeat(models.Model):
    """Expose durable worker availability without process-local state."""

    worker_id = models.CharField(primary_key=True, max_length=128)
    current_job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(auto_now_add=True)
    heartbeat_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-heartbeat_at"]


from .workflow_models import WorkflowRun, WorkflowRunEvent, WorkflowStatus  # noqa: E402, F401
