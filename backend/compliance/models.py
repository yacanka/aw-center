"""Canonical compliance-document aggregate and directly related evidence."""

import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from orgs.models import Panel, Project

from .compdoc_workflow import WORKFLOW_STATUS_CHOICES


STATUS_CHOICES = WORKFLOW_STATUS_CHOICES
LOI_CHOICES = [
    ("1", "1"),
    ("2", "2"),
    ("3", "3"),
    ("not_retained", "Not Retained"),
    ("retained", "Retained"),
]


class CoverPage(models.Model):
    """Canonical cover page shared by documents in one project."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="cover_pages",
    )
    number = models.CharField(max_length=32)
    issue = models.CharField(max_length=255, null=True, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    history = HistoricalRecords()

    class Meta:
        ordering = ["project__name", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "number"],
                name="compliance_unique_project_cover_page",
            )
        ]

    def __str__(self):
        return f"{self.project.slug}: {self.number}"


class ComplianceDocument(models.Model):
    """Project-scoped compliance register document with optimistic versioning."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="compliance_documents",
    )
    panel = models.ForeignKey(
        Panel,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="compliance_documents",
    )
    cover_page = models.ForeignKey(
        CoverPage,
        on_delete=models.PROTECT,
        related_name="compliance_documents",
    )
    name = models.CharField(max_length=256)
    signature_panel = models.JSONField(default=list, blank=True)
    tech_doc_no = models.CharField(max_length=64, null=True, blank=True)
    tech_doc_issue = models.CharField(max_length=255, null=True, blank=True)
    delivered_tech_doc_issue = models.CharField(max_length=255, null=True, blank=True)
    tech_doc_no_2 = models.CharField(max_length=64, null=True, blank=True)
    tech_doc_issue_2 = models.CharField(max_length=255, null=True, blank=True)
    delivered_tech_doc_issue_2 = models.CharField(max_length=255, null=True, blank=True)
    responsible = models.CharField(max_length=64, null=True, blank=True)
    cat = models.CharField(max_length=12, null=True, blank=True, choices=LOI_CHOICES)
    moc = models.CharField(max_length=1, null=True, blank=True)
    mom_no = models.CharField(max_length=128, null=True, blank=True)
    requirements = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="unknown",
        db_index=True,
        editable=False,
    )
    ubm_target_date = models.DateField(null=True, blank=True, db_index=True, editable=False)
    ubm_delivery_date = models.DateField(null=True, blank=True, db_index=True, editable=False)
    path = models.CharField(max_length=512, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_compliance_documents",
    )
    owner_group = models.ForeignKey(
        Group,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_compliance_documents",
    )
    next_action_due_date = models.DateField(null=True, blank=True, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archived_compliance_documents",
    )
    archive_reason = models.CharField(max_length=255, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "cover_page", "name"],
                name="compliance_unique_cover_page_document_name",
            ),
            models.UniqueConstraint(
                fields=["project", "cover_page", "tech_doc_no"],
                condition=Q(tech_doc_no__isnull=False) & ~Q(tech_doc_no=""),
                name="compliance_unique_cover_page_tech_doc",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "is_archived", "status"]),
            models.Index(fields=["project", "next_action_due_date"]),
        ]

    def clean(self):
        super().clean()
        if self.cover_page_id and self.cover_page.project_id != self.project_id:
            raise ValidationError({"cover_page": "Cover page must belong to the project."})
        if self.panel_id and self.panel.project_id != self.project_id:
            raise ValidationError({"panel": "Panel must belong to the project."})

    def __str__(self):
        return self.name


class WorkflowEvent(models.Model):
    """Immutable actor-attributed lifecycle transition."""

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Import"
        SYSTEM = "system", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        ComplianceDocument,
        on_delete=models.CASCADE,
        related_name="workflow_events",
    )
    sequence = models.PositiveIntegerField()
    previous_status = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    effective_date = models.DateField()
    next_action_due_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255)
    source = models.CharField(max_length=16, choices=Source.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_username = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "sequence"],
                name="compliance_unique_document_workflow_sequence",
            )
        ]
        indexes = [models.Index(fields=["document", "created_at"])]


class ReviewTask(models.Model):
    """Review or approval tied to the document version that was requested."""

    class Kind(models.TextChoices):
        REVIEW = "review", "Review"
        APPROVAL = "approval", "Approval"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        CANCELLED = "cancelled", "Cancelled"
        SUPERSEDED = "superseded", "Superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        ComplianceDocument,
        on_delete=models.CASCADE,
        related_name="review_tasks",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compliance_review_tasks",
    )
    assignee_username = models.CharField(max_length=150)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="requested_compliance_reviews",
    )
    requested_by_username = models.CharField(max_length=150)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_compliance_reviews",
    )
    decided_by_username = models.CharField(max_length=150, blank=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    request_note = models.CharField(max_length=500)
    decision_note = models.CharField(max_length=500, blank=True)
    source_version = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "kind", "assignee", "source_version"],
                condition=Q(status="pending"),
                name="compliance_unique_pending_review_source",
            )
        ]
        indexes = [
            models.Index(fields=["document", "status"]),
            models.Index(fields=["assignee", "status", "due_date"]),
        ]


class TrackingProfile(models.Model):
    class ResponsibleMode(models.TextChoices):
        AUTOMATIC = "automatic", "Automatic from panel"
        CUSTOM = "custom", "Custom selection"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.OneToOneField(
        ComplianceDocument,
        on_delete=models.CASCADE,
        related_name="tracking_profile",
    )
    responsible_mode = models.CharField(
        max_length=16,
        choices=ResponsibleMode.choices,
        default=ResponsibleMode.AUTOMATIC,
    )
    responsible_people = models.ManyToManyField(
        "orgs.Person",
        related_name="compliance_tracking_profiles",
        blank=True,
    )
    notification_enabled = models.BooleanField(default=False)
    notification_events = models.JSONField(default=list, blank=True)
    docproof_issue = models.CharField(max_length=32, blank=True)
    docproof_status = models.CharField(max_length=32, default="never_checked")
    docproof_checked_at = models.DateTimeField(null=True, blank=True)
    notification_checked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_compliance_tracking_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        TrackingProfile,
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    event_type = models.CharField(max_length=32)
    event_key = models.CharField(max_length=160, unique=True)
    message_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
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
        indexes = [models.Index(fields=["status", "next_attempt_at"])]


class NotificationPolicy(models.Model):
    """Immutable project policy revision; exactly one revision is active."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="compliance_notification_policies",
    )
    version = models.PositiveIntegerField()
    event_rules = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    change_note = models.CharField(max_length=255)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compliance_notification_policy_revisions",
    )
    updated_by_username = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "version"],
                name="compliance_unique_project_policy_version",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(is_active=True),
                name="compliance_unique_active_project_policy",
            ),
        ]


class ImportAudit(models.Model):
    """Sanitized evidence for preview/confirm tabular imports."""

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="compliance_import_audits",
    )
    source_filename = models.CharField(max_length=255)
    source_size = models.PositiveBigIntegerField(default=0)
    source_sha256 = models.CharField(max_length=64, editable=False)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compliance_import_audits",
    )
    request_id = models.CharField(max_length=64, blank=True)
    header_row = models.PositiveSmallIntegerField(null=True)
    mapped_columns = models.JSONField(default=list)
    unmapped_columns = models.JSONField(default=list)
    missing_columns = models.JSONField(default=list)
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    error_summary = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROCESSING)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    duration_ms = models.PositiveIntegerField(null=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["project", "started_at"])]


class DoorsImportMapping(models.Model):
    """Last successful source-to-target mapping for one project/module pair."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="doors_import_mappings",
    )
    module_path = models.CharField(max_length=1024)
    mapping = models.JSONField(default=dict)
    source_columns = models.JSONField(default=list)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="updated_doors_import_mappings",
    )
    successful_at = models.DateTimeField()

    class Meta:
        ordering = ["-successful_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "module_path"],
                name="compliance_unique_doors_import_mapping",
            )
        ]
        indexes = [models.Index(fields=["project", "successful_at"])]


class DocumentPurgeAudit(models.Model):
    """Content-free durable evidence for an explicitly purged document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_id = models.UUIDField(unique=True, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="compliance_document_purge_audits",
    )
    document_version = models.PositiveBigIntegerField(editable=False)
    purged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compliance_document_purge_audits",
    )
    purged_by_username = models.CharField(max_length=150)
    reason = models.CharField(max_length=255)
    purged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purged_at"]
        indexes = [models.Index(fields=["project", "purged_at"])]
