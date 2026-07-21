"""Project-wide compliance-document dashboard aggregation."""

from collections import Counter, defaultdict
from datetime import date, datetime

from django.utils import timezone

from common.compdoc_dashboard_timeline import build_timeline


STATUS_KEYS = (
    "to_be_issued",
    "airworthiness_review",
    "to_be_re-submitted",
    "to_be_updated",
    "authority_review",
    "authority_approved",
    "delayed",
    "unknown",
)
PENDING_BUCKETS = {
    "to_be_updated": "ubm",
    "airworthiness_review": "aw",
    "to_be_re-submitted": "aw",
    "authority_review": "authority",
}
DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")


def build_compdoc_dashboard(queryset, today=None):
    """Aggregate the complete queryset into a safe dashboard contract."""

    current_day = today or timezone.localdate()
    state = _empty_state(current_day)
    for document in queryset.iterator(chunk_size=500):
        _accumulate_document(state, document)
    return _serialize_state(state)


def _empty_state(current_day):
    return {
        "today": current_day,
        "total": 0,
        "statuses": Counter({key: 0 for key in STATUS_KEYS}),
        "panels": defaultdict(Counter),
        "pending_days": Counter({"authority": 0, "ubm": 0, "aw": 0}),
        "scheduled": Counter(),
        "actual": Counter(),
        "quality": Counter(),
    }


def _accumulate_document(state, document):
    state["total"] += 1
    entries = _normalize_flow(document["status_flow"], state["quality"])
    dated_entries = _parse_entries(entries, state["quality"])
    current_status = _current_status(dated_entries, state["today"])
    if current_status == "unknown":
        state["quality"]["unknown_status"] += 1
    state["statuses"][current_status] += 1
    _accumulate_panel(state, document.get("panel"), current_status)
    _accumulate_timeline(state, dated_entries)
    _accumulate_pending_days(state, dated_entries)


def _normalize_flow(raw_flow, quality):
    if not isinstance(raw_flow, list):
        quality["invalid_status_flow"] += 1
        return []
    entries = [item for item in raw_flow if _is_valid_entry(item)]
    if len(entries) != len(raw_flow):
        quality["invalid_status_flow"] += 1
    return entries


def _is_valid_entry(item):
    return isinstance(item, dict) and isinstance(item.get("status"), str) and item["status"].strip()


def _parse_entries(entries, quality):
    parsed = []
    for entry in entries:
        parsed_date = _parse_date(entry.get("date"))
        if parsed_date is None:
            quality["invalid_dates"] += 1
        parsed.append((entry["status"].strip(), parsed_date))
    return parsed


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


def _current_status(entries, today):
    if not entries:
        return "unknown"
    status, target_date = entries[-1]
    if len(entries) == 1 and status == "to_be_issued" and target_date and target_date < today:
        return "delayed"
    return status if status in STATUS_KEYS else "unknown"


def _accumulate_panel(state, panel, status):
    if not panel:
        state["quality"]["missing_panel"] += 1
        return
    state["panels"][str(panel)][status] += 1


def _accumulate_timeline(state, entries):
    if entries and entries[0][0] in {"to_be_issued", "delayed"} and entries[0][1]:
        state["scheduled"][entries[0][1]] += 1
    if len(entries) > 1 and entries[1][1]:
        state["actual"][entries[1][1]] += 1


def _accumulate_pending_days(state, entries):
    today = state["today"]
    for index, (status, started_at) in enumerate(entries):
        ended_at = entries[index + 1][1] if index + 1 < len(entries) else today
        if not started_at or not ended_at:
            continue
        elapsed = (ended_at - started_at).days
        if elapsed < 0:
            state["quality"]["out_of_order_dates"] += 1
            continue
        bucket = PENDING_BUCKETS.get(status)
        if bucket:
            state["pending_days"][bucket] += elapsed
        elif status == "to_be_issued" and index == len(entries) - 1 and elapsed > 0:
            state["pending_days"]["ubm"] += elapsed


def _serialize_state(state):
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
        "data_quality": _quality_summary(state["quality"]),
        "generated_at": timezone.now().isoformat(),
    }


def _serialize_panels(panels):
    result = []
    for panel, counts in sorted(panels.items(), key=lambda item: item[0].casefold()):
        values = {key: counts[key] for key in STATUS_KEYS}
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
