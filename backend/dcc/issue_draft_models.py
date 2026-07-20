"""Owned, reviewable JIRA issue drafts produced by AW Center workflows."""

import uuid

from django.conf import settings
from django.db import models


class JiraIssueDraftStatus(models.TextChoices):
    """Represent the explicit human-review and publication lifecycle."""

    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    PUBLISHING = "publishing", "Publishing"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"


class JiraIssueDraft(models.Model):
    """Store one owner-scoped JIRA draft derived from a verified analysis report."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jira_issue_drafts"
    )
    source_job = models.OneToOneField(
        "jobs.Job", on_delete=models.CASCADE, related_name="jira_issue_draft"
    )
    project_key = models.CharField(max_length=20)
    summary = models.CharField(max_length=255)
    description = models.TextField(max_length=30000)
    extra_fields = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=JiraIssueDraftStatus.choices, default=JiraIssueDraftStatus.DRAFT
    )
    version = models.PositiveIntegerField(default=1)
    marker_label = models.CharField(max_length=64, unique=True, editable=False)
    jira_issue_key = models.CharField(max_length=64, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_jira_issue_drafts",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="published_jira_issue_drafts",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    publish_started_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["owner", "status", "updated_at"])]
        permissions = [("publish_jiraissuedraft", "Can publish reviewed JIRA issue drafts")]


class JiraIssueDraftEvent(models.Model):
    """Record immutable, content-free lifecycle events for one draft."""

    draft = models.ForeignKey(JiraIssueDraft, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=32)
    version = models.PositiveIntegerField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
