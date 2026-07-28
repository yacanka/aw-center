"""Project-neutral tracking and notification records for compliance documents."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class CompDocTrackingProfile(models.Model):
    """Persist notification preferences without coupling project CompDoc tables."""

    class ResponsibleMode(models.TextChoices):
        AUTOMATIC = "automatic", "Automatic from ATA"
        CUSTOM = "custom", "Custom selection"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_slug = models.CharField(max_length=64)
    document_id = models.UUIDField()
    responsible_mode = models.CharField(
        max_length=16,
        choices=ResponsibleMode.choices,
        default=ResponsibleMode.AUTOMATIC,
    )
    responsible_person_ids = models.JSONField(default=list, blank=True)
    notification_enabled = models.BooleanField(default=False)
    notification_events = models.JSONField(default=list, blank=True)
    docproof_issue = models.CharField(max_length=32, blank=True)
    docproof_status = models.CharField(max_length=32, default="never_checked")
    docproof_checked_at = models.DateTimeField(null=True, blank=True)
    docproof_issue_detected_at = models.DateTimeField(null=True, blank=True)
    notification_checked_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_compdoc_tracking_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project_slug", "document_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project_slug", "document_id"],
                name="common_unique_compdoc_tracking_profile",
            )
        ]
        indexes = [
            models.Index(
                fields=["notification_enabled", "project_slug"],
                name="common_compdoc_notify_idx",
            )
        ]


class CompDocNotificationLog(models.Model):
    """Record content-free delivery evidence and idempotency state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        CompDocTrackingProfile,
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    event_type = models.CharField(max_length=32)
    event_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    recipient_count = models.PositiveSmallIntegerField(default=0)
    primary_recipient_count = models.PositiveSmallIntegerField(default=0)
    escalation_recipient_count = models.PositiveSmallIntegerField(default=0)
    policy_version = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["profile", "created_at"])]


class CompDocNotificationPolicy(models.Model):
    """Store one immutable, auditable project notification-policy revision."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_slug = models.CharField(max_length=64)
    version = models.PositiveIntegerField()
    event_rules = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    change_note = models.CharField(max_length=255)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compdoc_notification_policy_revisions",
    )
    updated_by_username = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["project_slug", "version"],
                name="common_unique_compdoc_policy_version",
            ),
            models.UniqueConstraint(
                fields=["project_slug"],
                condition=Q(is_active=True),
                name="common_unique_active_compdoc_policy",
            ),
        ]
        permissions = [
            ("manage_compdoc_notification_policy", "Can manage CompDoc notification policy")
        ]
