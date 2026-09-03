"""Canonical DCC persistence models."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class DccRecord(models.Model):
    """Project-scoped DCC tracking record without filesystem metadata."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dcc_records",
    )
    assigned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="assigned_dcc_records",
        blank=True,
    )
    projects = models.ManyToManyField(
        "orgs.Project",
        related_name="dcc_records",
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "issue", "id"]
        indexes = [models.Index(fields=["owner", "active", "updated_at"])]

    def __str__(self):
        return self.issue


class DccReminderDelivery(models.Model):
    """Durable watcher-reminder outbox entry with a bounded delivery lease."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(
        DccRecord,
        null=True,
        on_delete=models.SET_NULL,
        related_name="reminder_deliveries",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="dcc_reminder_deliveries",
    )
    idempotency_key = models.CharField(max_length=128)
    message_id = models.CharField(max_length=255, unique=True)
    subject = models.CharField(max_length=998)
    context = models.JSONField(default=dict)
    recipients = models.JSONField(default=list)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    recipient_count = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True, editable=False)
    claimed_at = models.DateTimeField(null=True, blank=True)
    claim_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="dcc_dccremi_status_18372b_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["requested_by", "idempotency_key"],
                condition=Q(requested_by__isnull=False),
                name="dcc_unique_reminder_idempotency",
            )
        ]


from .issue_draft_models import JiraIssueDraft, JiraIssueDraftEvent, JiraIssueDraftStatus  # noqa: E402, F401
