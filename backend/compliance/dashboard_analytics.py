"""Framework-independent Certification Dashboard calculations for web and desktop readers."""

from collections import Counter

from .dashboard_timeline import build_timeline
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
UNASSIGNED_PANEL_NAME = "Unassigned"


def aggregate_dashboard(slug, records, statuses, archived, current_day, generated_at):
    """Build all scopes from (flat document, ordered status/date entries) pairs."""
    overall = _empty_state()
    panels = {}
    panel_groups = {}
    for document, entries in records:
        panel_id = str(document["panel_id"]) if document["panel_id"] else "unassigned"
        if panel_id not in panels:
            panels[panel_id] = {
                "id": panel_id,
                "panel": document["panel"] if document["panel_id"] else UNASSIGNED_PANEL_NAME,
                "ata": document["ata"] if document["panel_id"] else "",
                "state": _empty_state(),
            }
        panel_name = panels[panel_id]["panel"]
        if panel_name not in panel_groups:
            panel_groups[panel_name] = {"chapters": set(), "state": _empty_state()}
        group = panel_groups[panel_name]
        if panels[panel_id]["ata"]:
            group["chapters"].add(panels[panel_id]["ata"])
        for state in (overall, panels[panel_id]["state"], group["state"]):
            _accumulate(state, document, entries, current_day)
    ordered_panels = sorted(
        panels.values(), key=lambda item: (item["panel"].casefold(), item["ata"])
    )
    return {
        "project": slug,
        "statuses": statuses,
        **_serialize(overall, current_day),
        "archived": archived,
        "panels": [
            {
                "id": panel["id"],
                "panel": panel["panel"],
                "ata": panel["ata"],
                "analytics": _serialize(panel["state"], current_day),
            }
            for panel in ordered_panels
        ],
        "generated_at": generated_at.isoformat(),
        "panel_groups": [
            {
                "id": f"panel:{name}",
                "panel": name,
                "ata": ", ".join(sorted(group["chapters"])),
                "analytics": _serialize(group["state"], current_day),
            }
            for name, group in sorted(panel_groups.items(), key=lambda item: item[0].casefold())
        ],
    }


def _empty_state():
    return {
        "total": 0,
        "overdue": 0,
        "statuses": Counter(),
        "chart_statuses": Counter(),
        "cats": Counter(),
        "issued_statuses": Counter(),
        "unissued_statuses": Counter(),
        "unissued_mocs": Counter(),
        "revised_scheduled": Counter(),
        "has_revised_target": False,
        "scheduled": Counter(),
        "actual": Counter(),
        "pending_days": Counter({"authority": 0, "ubm": 0, "aw": 0}),
        "quality": Counter(),
        "risk": create_risk_state(),
    }


def _accumulate(state, document, entries, today):
    current_target = document["revised_target_date"] or document["target_date"]
    state["total"] += 1
    state["statuses"][document["status"]] += 1
    state["cats"][(document["cat"] or "").strip()] += 1
    status = _chart_status(document, today)
    publication = publication_status(document, today)
    state["chart_statuses"][publication] += 1
    if document["release_date"]:
        state["issued_statuses"][publication] += 1
    else:
        state["unissued_statuses"][publication] += 1
        state["unissued_mocs"][(document["moc"] or "").strip()] += 1
    if document["next_action_due_date"] and document["next_action_due_date"] < today:
        state["overdue"] += 1
    if document["target_date"]:
        state["scheduled"][document["target_date"]] += 1
    if current_target:
        state["revised_scheduled"][current_target] += 1
    state["has_revised_target"] |= bool(document["revised_target_date"])
    if document["release_date"]:
        state["actual"][document["release_date"]] += 1
    state["quality"]["missing_panel"] += not document["panel_id"]
    state["quality"]["blank_cover_page"] += not document["cover_page_no"].strip()
    state["quality"]["unknown_status"] += status == "unknown"
    _accumulate_pending(state, entries, today)
    # Initial planned dates can precede any workflow event in imported records.
    if not entries and status == "delayed":
        state["pending_days"]["ubm"] += (today - current_target).days
    accumulate_document_risk(
        state["risk"], document,
        entries, status, today, DEFAULT_RISK_POLICY,
    )


def publication_status(document, today):
    """Delivery is the publication evidence, independent of workflow status."""
    if document["release_date"]:
        return document["status"] or "unknown"
    target = document["revised_target_date"] or document["target_date"]
    if not target:
        return "missing_target"
    return "delayed" if target < today else "expected"


def _chart_status(document, today):
    current_target = document["revised_target_date"] or document["target_date"]
    if (
        document["status"] == "to_be_issued"
        and current_target
        and current_target < today
        and not document["release_date"]
    ):
        return "delayed"
    return document["status"] or "unknown"


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
    scheduled = sum(count for day, count in state["revised_scheduled"].items() if day <= today)
    return {
        "total": total,
        "overdue": state["overdue"],
        # Publication/deadline buckets are dashboard projections. Preserve the
        # canonical workflow counts and never persist the projected statuses.
        "status_counts": dict(state["statuses"]),
        "chart_status_counts": dict(state["chart_statuses"]),
        "cat_counts": dict(state["cats"]),
        "publication": {
            "issued": _publication_group(state["issued_statuses"]),
            "not_issued": _publication_group(state["unissued_statuses"]),
        },
        "unissued_moc_counts": dict(state["unissued_mocs"]),
        "pending_days": dict(state["pending_days"]),
        "timeline": build_timeline(
            state["scheduled"], state["actual"], total, today,
            revised=state["revised_scheduled"] if state["has_revised_target"] else None,
        ),
        "performance": {
            "scheduled": _metric(scheduled, total),
            "actual": _metric(sum(state["actual"].values()), total),
            "approved": _metric(state["statuses"]["authority_approved"], total),
        },
        "risk": serialize_risk(state["risk"], total),
        "data_quality": {"issue_count": sum(quality.values()), **quality},
    }


def _publication_group(counts):
    return {"total": sum(counts.values()), "status_counts": dict(counts)}


def _metric(filled, total):
    return {
        "filled": filled,
        "empty": total - filled,
        "percentage": round(filled / total * 100) if total else 0,
    }
