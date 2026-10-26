"""Server-calculated portfolio metrics and immutable report capture."""

import hashlib
from datetime import timedelta

from django.utils import timezone

from common.compdoc_dashboard import build_compdoc_dashboard
from common.compdoc_operations_summary import build_operational_summary
from common.compdoc_risk import get_dashboard_value_fields
from management_reports.access import project_model
from management_reports.models import ReportSnapshot

SCHEMA_VERSION = 1
METRIC_KEYS = (
    "document_count",
    "issued_count",
    "approved_count",
    "approval_percentage",
    "scheduled_count",
    "schedule_variance",
    "high_risk_count",
    "action_overdue_count",
    "action_due_soon_count",
    "unassigned_count",
    "pending_review_count",
    "pending_approval_count",
    "data_quality_issue_count",
)


def scope_key(slugs):
    return hashlib.sha256(",".join(sorted(slugs)).encode("utf-8")).hexdigest()


def monday_of(value):
    return value - timedelta(days=value.weekday())


def build_report(definitions, title="Executive summary", management_note=""):
    """Capture current metrics using the existing dashboard definitions."""
    captured_at = timezone.now()
    projects, priorities = [], []
    for definition in definitions:
        metrics, project_priorities = _project_report(
            definition, timezone.localdate(captured_at)
        )
        projects.append({
            "slug": definition.slug,
            "display_name": definition.display_name,
            **metrics,
        })
        priorities.extend(project_priorities)
    totals = {key: sum(item[key] for item in projects) for key in METRIC_KEYS}
    totals["approval_percentage"] = _percentage(
        totals["approved_count"], totals["document_count"]
    )
    priorities.sort(key=lambda item: (
        -item["score"], -item["stage_age_days"],
        item["name"].casefold(), item["document_id"],
    ))
    return {
        "id": None,
        "title": title,
        "management_note": management_note,
        "captured_at": captured_at.isoformat(),
        "week_start": monday_of(timezone.localdate(captured_at)).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "project_slugs": sorted(item.slug for item in definitions),
        "totals": totals,
        "projects": projects,
        "priorities": priorities[:5],
    }


def capture_report(user, definitions, title, management_note):
    """Persist only server-calculated metrics and the validated author inputs."""
    report = build_report(definitions, title, management_note)
    snapshot = ReportSnapshot(
        owner=user,
        captured_at=report["captured_at"],
        week_start=report["week_start"],
        schema_version=report["schema_version"],
        scope_key=scope_key(report["project_slugs"]),
        project_slugs=report["project_slugs"],
        payload=report,
    )
    report["id"] = str(snapshot.pk)
    snapshot.save(force_insert=True)
    return snapshot


def report_list_item(snapshot):
    return {
        "id": str(snapshot.pk),
        "title": snapshot.payload["title"],
        "captured_at": snapshot.captured_at.isoformat(),
        "week_start": snapshot.week_start.isoformat(),
        "schema_version": snapshot.schema_version,
        "project_slugs": snapshot.project_slugs,
    }


def _project_report(definition, today):
    model = project_model(definition)
    rows = model.objects.filter(is_archived=False).values(
        *get_dashboard_value_fields(model)
    )
    panel_model = model._meta.apps.get_model(model._meta.app_label, "Panel")
    dashboard = build_compdoc_dashboard(
        rows,
        today=today,
        valid_panel_pairs=set(panel_model.objects.values_list("name", "ata")),
    )
    operations = build_operational_summary(model, today=today)
    metrics = _metrics(dashboard, operations)
    priorities = dashboard["risk"]["priorities"][:5]
    documents = model.objects.filter(
        pk__in=[item["document_id"] for item in priorities],
        is_archived=False,
    ).select_related("owner", "owner_group")
    context = {str(item.pk): item for item in documents}
    return metrics, [
        _priority(item, definition, context[item["document_id"]])
        for item in priorities if item["document_id"] in context
    ]


def _metrics(dashboard, operations):
    metrics = {
        "document_count": dashboard["document_count"],
        "issued_count": dashboard["performance"]["actual"]["filled"],
        "approved_count": dashboard["performance"]["approved"]["filled"],
        "scheduled_count": dashboard["performance"]["scheduled"]["filled"],
        "high_risk_count": dashboard["risk"]["counts"]["high"],
        "action_overdue_count": operations["action_overdue"],
        "action_due_soon_count": operations["action_due_soon"],
        "unassigned_count": operations["unassigned"],
        "pending_review_count": operations["pending_review"],
        "pending_approval_count": operations["pending_approval"],
        "data_quality_issue_count": dashboard["data_quality"]["issue_count"],
    }
    metrics["approval_percentage"] = _percentage(
        metrics["approved_count"], metrics["document_count"]
    )
    metrics["schedule_variance"] = metrics["issued_count"] - metrics["scheduled_count"]
    return metrics


def _priority(item, definition, document):
    owner = None
    if document.owner:
        owner = document.owner.get_username()
    elif document.owner_group:
        owner = document.owner_group.name
    fields = ("document_id", "name", "status", "score", "level", "stage_age_days")
    return {
        **{key: item[key] for key in fields},
        "project_slug": definition.slug,
        "project_name": definition.display_name,
        "reason": "; ".join(signal["detail"] for signal in item["signals"]),
        "owner": owner,
        "next_action_due_date": (
            document.next_action_due_date.isoformat()
            if document.next_action_due_date else None
        ),
    }


def _percentage(approved, count):
    return round(approved * 100 / count, 1) if count else 0.0
