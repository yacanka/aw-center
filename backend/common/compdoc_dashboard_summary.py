"""Serialization helpers for compliance-document dashboard analytics."""

from django.utils import timezone

from common.compdoc_dashboard_timeline import build_timeline
from common.compdoc_risk import serialize_risk


def serialize_dashboard_state(state, risk_policy):
    """Return the complete stable dashboard response contract."""

    timeline = build_timeline(
        state["scheduled"], state["actual"], state["total"], state["today"]
    )
    statuses = dict(state["statuses"])
    return {
        "document_count": state["total"],
        "status_counts": statuses,
        "panels": _serialize_panels(state["panels"]),
        "pending_days": dict(state["pending_days"]),
        "timeline": timeline,
        "performance": _performance(state["total"], statuses, timeline),
        "risk": serialize_risk(state["risk"], state["total"], risk_policy),
        "data_quality": _quality_summary(state["quality"]),
        "generated_at": timezone.now().isoformat(),
    }


def _serialize_panels(panels):
    result = []
    for panel, counts in sorted(panels.items(), key=lambda item: item[0].casefold()):
        values = dict(counts)
        result.append({"panel": panel, "total": sum(values.values()), **values})
    return result


def _performance(total, statuses, timeline):
    scheduled_remaining = (timeline["last_scheduled"] or {}).get("y", total)
    actual_remaining = statuses["to_be_issued"] + statuses["delayed"]
    return {
        "scheduled": _metric(total - scheduled_remaining, total),
        "actual": _metric(total - actual_remaining, total),
        "approved": _metric(statuses["authority_approved"], total),
    }


def _metric(filled, total):
    percentage = round((filled / total) * 100) if total else 0
    return {"filled": filled, "empty": total - filled, "percentage": percentage}


def _quality_summary(quality):
    keys = (
        "invalid_status_flow",
        "invalid_dates",
        "out_of_order_dates",
        "missing_panel",
        "unknown_status",
    )
    values = {key: quality[key] for key in keys}
    return {"issue_count": sum(values.values()), **values}
