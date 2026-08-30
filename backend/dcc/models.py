"""Canonical DCC persistence models."""

import uuid

from django.conf import settings
from django.db import models


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


from .issue_draft_models import JiraIssueDraft, JiraIssueDraftEvent, JiraIssueDraftStatus  # noqa: E402, F401
