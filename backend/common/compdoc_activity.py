"""Safe unified activity payloads for compliance documents."""


def build_activity_items(document, events, reviews, history_limit=100):
    """Merge workflow, review, and Simple History evidence."""

    items = [_event_payload(item) for item in events]
    items.extend(_review_payload(item) for item in reviews)
    items.extend(_history_payloads(document, history_limit))
    return sorted(items, key=lambda item: item["occurred_at"], reverse=True)


def _event_payload(item):
    return {
        "type": "workflow",
        "occurred_at": item.created_at,
        "actor": item.actor_username,
        "reason": item.reason,
        "status": item.status,
        "previous_status": item.previous_status,
    }


def _review_payload(item):
    return {
        "type": item.kind,
        "occurred_at": item.decided_at or item.created_at,
        "actor": item.decided_by_username or item.requested_by_username,
        "status": item.status,
        "reason": item.decision_note or item.request_note,
    }


def _history_payloads(document, limit):
    records = list(
        document.history.select_related("history_user").order_by(
            "-history_date", "-history_id"
        )[: limit + 1]
    )
    payloads = []
    for index, current in enumerate(records[:limit]):
        older = records[index + 1] if index + 1 < len(records) else None
        payloads.append(_history_payload(current, older))
    return payloads


def _history_payload(current, older):
    return {
        "type": "history",
        "occurred_at": current.history_date,
        "actor": str(current.history_user or "System"),
        "reason": current.history_change_reason or "Document created",
        "changes": _history_changes(current, older),
    }


def _history_changes(current, older):
    if older is None:
        return [{"field": "document", "changed": True}]
    changes = []
    for change in current.diff_against(older).changes:
        payload = {"field": change.field, "changed": True}
        if change.field != "path":
            payload.update({"old": _safe_value(change.old), "new": _safe_value(change.new)})
        changes.append(payload)
    return changes


def _safe_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:20]]
    return str(value)[:256]
