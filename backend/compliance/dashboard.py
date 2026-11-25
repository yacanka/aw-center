"""Read-only project and panel analytics for the canonical compliance aggregate."""

from re import escape

from django.db.models import Prefetch, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .dashboard_analytics import UNASSIGNED_PANEL_NAME, aggregate_dashboard
from .models import ComplianceDocument, DocumentStatus, WorkflowEvent


UNISSUED_BUCKETS = ("delayed", "expected", "missing_target")
# Match Python's str.strip() character set in both SQLite and PostgreSQL.
CAT_PADDING = "[\x09-\x0d\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*"


def build_dashboard(project, *, today=None):
    """Aggregate all active documents, independent of table pagination.

    ATA and named-panel analytics share one snapshot so every chart and risk list
    can switch scope together without fetching document bodies in the browser.
    Related events are prefetched in bounded batches; priorities are capped at 25
    per scope. No workflow, history, tracking or document state is mutated.
    """
    current_day = today or timezone.localdate()
    documents = ComplianceDocument.objects.filter(project=project)
    active = (
        documents.filter(is_archived=False)
        .select_related("panel", "cover_page")
        .only(
            "id", "name", "status", "cat", "moc", "target_date", "revised_target_date", "release_date",
            "next_action_due_date",
            "panel__id", "panel__name", "panel__ata", "cover_page__number",
        )
        .prefetch_related(Prefetch(
            "workflow_events",
            queryset=WorkflowEvent.objects.only(
                "document_id", "sequence", "status", "effective_date",
            ).order_by("sequence"),
            to_attr="dashboard_events",
        ))
    )
    records = (_dashboard_record(document) for document in active.iterator(chunk_size=500))
    return aggregate_dashboard(
        project.slug, records,
        list(DocumentStatus.objects.filter(project=project).values("value", "label")),
        documents.filter(is_archived=True).count(), current_day, timezone.now(),
    )


def _dashboard_record(document):
    fields = {
        "id": document.pk,
        "name": document.name,
        "status": document.status,
        "cat": document.cat,
        "moc": document.moc,
        "panel_id": document.panel_id,
        "panel": document.panel.name if document.panel_id else None,
        "ata": document.panel.ata if document.panel_id else None,
        "cover_page_no": document.cover_page.number,
        "target_date": document.target_date,
        "revised_target_date": document.revised_target_date,
        "release_date": document.release_date,
        "next_action_due_date": document.next_action_due_date,
    }
    return fields, [(event.status, event.effective_date) for event in document.dashboard_events]


def filter_dashboard_slice(queryset, *, delivery=None, cat=None, panel=None, panel_id=None):
    """Match an active dashboard slice within an already project-scoped queryset."""
    queryset = queryset.filter(is_archived=False)
    if panel is not None:
        scope = Q(panel__name=panel)
        if panel == UNASSIGNED_PANEL_NAME:
            scope |= Q(panel__isnull=True)
        queryset = queryset.filter(scope)
    if panel_id is not None:
        queryset = queryset.filter(panel_id=None if panel_id == "unassigned" else panel_id)
    if cat is not None:
        pattern = f"^{CAT_PADDING}{escape(cat)}{CAT_PADDING}$" if cat else f"^{CAT_PADDING}$"
        category = Q(cat__regex=pattern)
        if not cat:
            category |= Q(cat__isnull=True)
        queryset = queryset.filter(category)
    return _filter_delivery_slice(queryset, delivery) if delivery else queryset


def _filter_delivery_slice(queryset, delivery):
    if delivery.startswith("issued:"):
        status = delivery.removeprefix("issued:")
        statuses = ("unknown", "") if status == "unknown" else (status,)
        return queryset.filter(release_date__isnull=False, status__in=statuses)
    unissued = queryset.filter(release_date__isnull=True).alias(
        dashboard_target=Coalesce("revised_target_date", "target_date"),
    )
    if delivery == "missing_target":
        return unissued.filter(dashboard_target__isnull=True)
    lookup = "dashboard_target__lt" if delivery == "delayed" else "dashboard_target__gte"
    return unissued.filter(**{lookup: timezone.localdate()})
