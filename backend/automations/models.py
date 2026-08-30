"""Feature-owned state for reviewed, durable automation workflows."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from jobs.storage import private_job_storage


def ecr_source_path(instance, _filename):
    """Store an ECR source behind an opaque owner-scoped private path."""

    return f"automations/ecr/{instance.owner_id}/{instance.id}/source.pdf"


class EcrWorkflowStatus(models.TextChoices):
    """Represent the explicit review and external-publication lifecycle."""

    REVIEW = "review", "Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    PUBLISHING = "publishing", "Publishing"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    RECONCILIATION_REQUIRED = (
        "reconciliation_required",
        "Reconciliation required",
    )


class EcrWorkflow(models.Model):
    """Store one owner-scoped, immutable ECR review and publication plan."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ecr_workflows",
    )
    projects = models.ManyToManyField(
        "orgs.Project",
        related_name="ecr_workflows",
    )
    source_pdf = models.FileField(
        storage=private_job_storage,
        upload_to=ecr_source_path,
        max_length=500,
    )
    source_sha256 = models.CharField(max_length=64)
    create_idempotency_key = models.CharField(max_length=128, blank=True)
    snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=EcrWorkflowStatus.choices,
        default=EcrWorkflowStatus.REVIEW,
    )
    version = models.PositiveIntegerField(default=1)
    project_key = models.CharField(max_length=20, blank=True)
    extra_fields = models.JSONField(default=dict, blank=True)
    selected_subtasks = models.JSONField(default=list, blank=True)
    marker_label = models.CharField(max_length=64, unique=True, editable=False)
    jira_issue_key = models.CharField(max_length=64, blank=True)
    publication_state = models.JSONField(default=dict, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_ecr_workflows",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    publish_started_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    publication_job = models.OneToOneField(
        "jobs.Job",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ecr_publication_workflow",
    )
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["owner", "status", "updated_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "create_idempotency_key"],
                condition=~Q(create_idempotency_key=""),
                name="automations_unique_owner_ecr_create_key",
            )
        ]


class EcrWorkflowEvent(models.Model):
    """Record bounded, content-free ECR lifecycle events."""

    workflow = models.ForeignKey(
        EcrWorkflow,
        on_delete=models.CASCADE,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
    )
    event_type = models.CharField(max_length=40)
    version = models.PositiveIntegerField()
    code = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
