from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class JIRA_DCC(models.Model):
    class Meta:
        ordering = ["-created_time", "issue", "id"]

    issue = models.CharField(max_length=255)
    ecd_name = models.CharField(max_length=255)
    dcc_path = models.CharField(max_length=512, verbose_name="DCC Folder Path", null=True, blank=True, )
    active = models.BooleanField(help_text="If it is active, then it will check the issue on JIRA")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dcc")
    created_time = models.DateTimeField(default=timezone.now, editable=False)
    last_reminder_mail_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

    def __str__(self):
        return self.issue


class DccCompdocTrace(models.Model):
    """Persist immutable CompDoc provenance for a confirmed DCC creation chain."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_id = models.UUIDField(db_index=True)
    job_input_sha256 = models.CharField(max_length=64, db_index=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="dcc_compdoc_traces",
    )
    issue_key = models.CharField(max_length=64)
    project_slug = models.CharField(max_length=64)
    compdoc_id = models.UUIDField()
    source_history_id = models.BigIntegerField(null=True)
    source_history_at = models.DateTimeField(null=True)
    snapshot_fingerprint = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-confirmed_at", "issue_key", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job_id", "project_slug", "compdoc_id"],
                name="dcc_unique_job_compdoc_trace",
            ),
        ]
        indexes = [
            models.Index(
                fields=["project_slug", "compdoc_id", "confirmed_at"],
                name="dcc_compdoc_history_idx",
            ),
            models.Index(
                fields=["confirmed_by", "job_input_sha256"],
                name="dcc_trace_source_idx",
            ),
        ]

    def __str__(self):
        return f"{self.issue_key}: {self.project_slug}/{self.compdoc_id}"


from .issue_draft_models import JiraIssueDraft, JiraIssueDraftEvent, JiraIssueDraftStatus  # noqa: E402, F401
