"""Private server-calculated management report captures."""
import uuid

from django.conf import settings
from django.db import models


class ReportSnapshot(models.Model):
    """An immutable API capture; permissions remain live even when data is historical."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    captured_at = models.DateTimeField()
    week_start = models.DateField()
    schema_version = models.PositiveSmallIntegerField(default=1)
    scope_key = models.CharField(max_length=64)
    project_slugs = models.JSONField(default=list)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["-captured_at", "-id"]
        indexes = [models.Index(fields=["owner", "scope_key", "week_start"], name="mgmt_owner_scope_week_idx")]
