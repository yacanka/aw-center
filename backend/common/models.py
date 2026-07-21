from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import RegexValidator
from simple_history.models import HistoricalRecords
import uuid

from .cover_page_models import CoverPage
from .compdoc_workflow import WORKFLOW_STATUS_CHOICES, extract_workflow_projection

STATUS_CHOICES = WORKFLOW_STATUS_CHOICES


LOI_CHOICES = [
    ("1", "1"),
    ("2", "2"),
    ("3", "3"),
    ("not_retained", "Not Retained"),
    ("retained", "Retained"),
]

class CompDocBase(models.Model):
    class Meta:
        abstract = True
        ordering = ["-created_time", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cover_page", "name"],
                name="%(app_label)s_unique_cover_page_compdoc",
            ),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    panel = models.CharField(max_length=128, null=True, blank=True)
    signature_panel = models.JSONField(default=list, null=True, blank=True)
    ata = models.CharField(
        max_length=5,
        default="00-00",
        validators=[
            RegexValidator(r'^[0-9]{2}-[0-9]{2}$', message="Ata chapter must consist of four digits (XX-XX)."),
        ]
    )
    name = models.CharField(max_length=256)

    cover_page = models.ForeignKey(
        CoverPage,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_compliance_documents",
        editable=False,
    )
    cover_page_no = models.CharField(default=uuid.uuid4, max_length=32)
    cover_page_issue = models.CharField(null=True, blank=True)
    tech_doc_no = models.CharField(max_length=64, null=True, blank=True)
    tech_doc_issue = models.CharField(null=True, blank=True)
    delivered_tech_doc_issue = models.CharField(null=True, blank=True)

    responsible = models.CharField(max_length=64, null=True, blank=True)
    cat = models.CharField(max_length=12, null=True, blank=True, choices=LOI_CHOICES)
    moc = models.CharField(max_length=1, null=True, blank=True)
    mom_no = models.CharField(max_length=128, null=True, blank=True)

    requirements = models.JSONField(default=list, null=True, blank=True)
    status_flow = models.JSONField(default=list, null=True, blank=True)
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

    history = HistoricalRecords(inherit=True)

    created_time = models.DateTimeField(default=timezone.now, editable=False)

    def save(self, *args, **kwargs):
        """Resolve the canonical project cover page before saving the document."""

        cover_page, cover_page_changed = self._resolve_cover_page()
        self._sync_workflow_projection()
        self.cover_page = cover_page
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {
                *kwargs["update_fields"],
                "cover_page",
                "status",
                "ubm_target_date",
                "ubm_delivery_date",
            }
        super().save(*args, **kwargs)
        if cover_page_changed:
            self._sync_legacy_cover_page_fields()

    def _resolve_cover_page(self):
        cover_page, created = CoverPage.objects.get_or_create(
            project_slug=self._meta.app_label,
            number=str(self.cover_page_no).strip(),
            defaults={"issue": self.cover_page_issue},
        )
        issue_changed = not created and cover_page.issue != self.cover_page_issue
        if issue_changed:
            cover_page.issue = self.cover_page_issue
            cover_page.save(update_fields=["issue"])
        return cover_page, created or issue_changed

    def _sync_workflow_projection(self):
        projection = extract_workflow_projection(self.status_flow)
        self.status = projection.status
        self.ubm_target_date = projection.target_date
        self.ubm_delivery_date = projection.delivery_date

    def _sync_legacy_cover_page_fields(self):
        type(self).objects.filter(cover_page=self.cover_page).exclude(pk=self.pk).update(
            cover_page_no=self.cover_page.number,
            cover_page_issue=self.cover_page.issue,
        )

    def __str__(self):
        return self.name

class PanelBase(models.Model):
    class Meta:
        abstract = True
        ordering = ["ata", "name"]

    name = models.CharField()
    discipline = models.CharField()
    ata = models.CharField(
        max_length=5,
        unique=True,
        validators=[
            RegexValidator(r'^[0-9]{2}-[0-9]{2}$', message="Ata chapter must consist of four digits (XX-XX)."),
        ],
    )

    def __str__(self):
        return self.name

class Titles(models.TextChoices):
    AS = "AS", "AS"
    CVE = "CVE", "CVE"
    IPT = "IPT", "IPT"
    SSB = "SSB", "SSB"
    AF = "Air Force", "Air Force"
    PSK = "PSK", "PSK"
    PCE = "PCE", "PCE"

class ResponsibleBase(models.Model):
    class Meta:
        abstract = True
        ordering = ["name", "person_id"]

    person_id = models.CharField(max_length=6)
    name = models.CharField()
    email = models.EmailField()
    title = models.CharField(choices=Titles.choices)

    def __str__(self):
        return self.name


class CompDocImportAudit(models.Model):
    """Record a sanitized compliance-document import lifecycle."""

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_slug = models.CharField(max_length=64, db_index=True)
    source_filename = models.CharField(max_length=255)
    source_size = models.PositiveBigIntegerField(default=0)
    source_sha256 = models.CharField(max_length=64, editable=False)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compdoc_import_audits",
    )
    imported_by_username = models.CharField(max_length=150)
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
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PROCESSING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    duration_ms = models.PositiveIntegerField(null=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["project_slug", "started_at"])]


from .action_center_models import ActionCenterDecision  # noqa: E402,F401
