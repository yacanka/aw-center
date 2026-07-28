"""Immutable workflow and review evidence for project compliance documents."""

import uuid

from django.conf import settings
from django.db import models


class CompDocWorkflowEvent(models.Model):
    """Record one immutable, actor-attributed lifecycle transition."""

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Import"
        MIGRATION = "migration", "Migration"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_slug = models.CharField(max_length=64)
    document_id = models.UUIDField()
    sequence = models.PositiveIntegerField()
    previous_status = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32)
    effective_date = models.DateField()
    next_action_due_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255)
    source = models.CharField(max_length=16, choices=Source.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_username = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["project_slug", "document_id", "sequence"],
                name="common_unique_compdoc_workflow_sequence",
            )
        ]
        indexes = [models.Index(fields=["project_slug", "document_id", "created_at"])]


class CompDocReviewTask(models.Model):
    """Track an informational review or approval assigned to an AW Center user."""

    class Kind(models.TextChoices):
        REVIEW = "review", "Review"
        APPROVAL = "approval", "Approval"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_slug = models.CharField(max_length=64)
    document_id = models.UUIDField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compdoc_review_tasks",
    )
    assignee_username = models.CharField(max_length=150)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="requested_compdoc_reviews",
    )
    requested_by_username = models.CharField(max_length=150)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="decided_compdoc_reviews",
    )
    decided_by_username = models.CharField(max_length=150, blank=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    request_note = models.CharField(max_length=500)
    decision_note = models.CharField(max_length=500, blank=True)
    source_history_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project_slug", "document_id", "status"]),
            models.Index(fields=["assignee", "status", "due_date"]),
        ]
        permissions = [("manage_compdoc_workflow", "Can manage CompDoc workflow tasks")]
