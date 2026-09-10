"""Read-only project and panel analytics for the canonical compliance aggregate."""

from collections import Counter

from django.db.models import Prefetch
from django.utils import timezone

from .compdoc_workflow import WORKFLOW_STATUSES
from .dashboard_timeline import build_timeline
from .models import ComplianceDocument, WorkflowEvent
from .risk import (
    DEFAULT_RISK_POLICY,
    accumulate_document_risk,
    create_risk_state,
    serialize_risk,
)


PENDING_BUCKETS = {
    "to_be_updated": "ubm",
    "airworthiness_review": "aw",
    "to_be_re-submitted": "aw",
    "authority_review": "authority",
}
QUALITY_KEYS = ("missing_panel", "unknown_status", "blank_cover_page", "out_of_order_dates")


def build_dashboard(project, *, today=None):
    """Aggregate all active documents, independent of table pagination.

    Panel analytics are returned in the same snapshot so every chart and risk
    list can switch scope together without fetching document bodies in the browser.
    Related events are prefetched in bounded batches; priorities are capped at 25
    per scope. No workflow, history, tracking or document state is mutated.
    """
    current_day = today or timezone.localdate()
    documents = ComplianceDocument.objects.filter(project=project)
    active = (
        documents.filter(is_archived=False)
        .select_related("panel", "cover_page")
        .only(
            "id", "name", "status", "ubm_target_date", "ubm_delivery_date",
            "next_action_due_date", "tech_doc_no", "tech_doc_no_2",
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
    overall = _empty_state()
    panels = {}
    for document in active.iterator(chunk_size=500):
        panel_id = str(document.panel_id) if document.panel_id else "unassigned"
        if panel_id not in panels:
            panels[panel_id] = {
                "id": panel_id,
                "panel": document.panel.name if document.panel_id else "Unassigned",
                "ata": document.panel.ata if document.panel_id else "",
                "state": _empty_state(),
            }
        entries = [(event.status, event.effective_date) for event in document.dashboard_events]
        for state in (overall, panels[panel_id]["state"]):
            _accumulate(state, document, entries, current_day)
    ordered_panels = sorted(
        panels.values(), key=lambda item: (item["panel"].casefold(), item["ata"])
    )
    return {
        "project": project.slug,
        **_serialize(overall, current_day),
        "archived": documents.filter(is_archived=True).count(),
        "panels": [
            {
                "id": panel["id"],
                "panel": panel["panel"],
                "ata": panel["ata"],
                "analytics": _serialize(panel["state"], current_day),
            }
            for panel in ordered_panels
        ],
        "generated_at": timezone.now().isoformat(),
    }


def _empty_state():
    return {
        "total": 0,
        "overdue": 0,
        "statuses": Counter(),
        "chart_statuses": Counter(),
        "scheduled": Counter(),
        "actual": Counter(),
        "pending_days": Counter({"authority": 0, "ubm": 0, "aw": 0}),
        "quality": Counter(),
        "risk": create_risk_state(),
    }


def _accumulate(state, document, entries, today):
    state["total"] += 1
    state["statuses"][document.status] += 1
    status = _chart_status(document, today)
    state["chart_statuses"][status] += 1
    if document.next_action_due_date and document.next_action_due_date < today:
        state["overdue"] += 1
    if document.ubm_target_date:
        state["scheduled"][document.ubm_target_date] += 1
    if document.ubm_delivery_date and document.ubm_delivery_date <= today:
        state["actual"][document.ubm_delivery_date] += 1
    state["quality"]["missing_panel"] += not document.panel_id
    state["quality"]["blank_cover_page"] += not document.cover_page.number.strip()
    state["quality"]["unknown_status"] += status == "unknown"
    _accumulate_pending(state, entries, today)
    # Initial planned dates can precede any workflow event in imported records.
    if not entries and status == "delayed":
        state["pending_days"]["ubm"] += (today - document.ubm_target_date).days
    accumulate_document_risk(
        state["risk"],
        {
            "id": document.pk,
            "name": document.name,
            "panel": document.panel.name if document.panel_id else None,
            "ata": document.panel.ata if document.panel_id else None,
            "tech_doc_no": document.tech_doc_no,
            "tech_doc_no_2": document.tech_doc_no_2,
            "ubm_target_date": document.ubm_target_date,
        },
        entries, status, today, DEFAULT_RISK_POLICY,
    )


def _chart_status(document, today):
    if (
        document.status == "to_be_issued"
        and document.ubm_target_date
        and document.ubm_target_date < today
        and not document.ubm_delivery_date
    ):
        return "delayed"
    return document.status if document.status in WORKFLOW_STATUSES else "unknown"


def _accumulate_pending(state, entries, today):
    for index, (status, started_at) in enumerate(entries):
        next_date = entries[index + 1][1] if index + 1 < len(entries) else None
        if next_date and next_date < started_at:
            state["quality"]["out_of_order_dates"] += 1
            continue
        elapsed = max(0, (min(next_date or today, today) - started_at).days)
        bucket = PENDING_BUCKETS.get(status)
        if bucket:
            state["pending_days"][bucket] += elapsed
        elif status == "to_be_issued" and next_date is None:
            state["pending_days"]["ubm"] += elapsed


def _serialize(state, today):
    total = state["total"]
    quality = {key: state["quality"][key] for key in QUALITY_KEYS}
    scheduled = sum(count for day, count in state["scheduled"].items() if day <= today)
    return {
        "total": total,
        "overdue": state["overdue"],
        # Keep the existing API's canonical status counts. Delay is a chart-only
        # projection, never a new persisted workflow state.
        "status_counts": dict(state["statuses"]),
        "chart_status_counts": dict(state["chart_statuses"]),
        "pending_days": dict(state["pending_days"]),
        "timeline": build_timeline(state["scheduled"], state["actual"], total, today),
        "performance": {
            "scheduled": _metric(scheduled, total),
            "actual": _metric(sum(state["actual"].values()), total),
            "approved": _metric(state["statuses"]["authority_approved"], total),
        },
        "risk": serialize_risk(state["risk"], total),
        "data_quality": {"issue_count": sum(quality.values()), **quality},
    }


def _metric(filled, total):
    return {
        "filled": filled,
        "empty": total - filled,
        "percentage": round(filled / total * 100) if total else 0,
    }
