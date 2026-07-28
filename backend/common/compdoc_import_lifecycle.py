"""Lifecycle safeguards for compliance-document imports."""

from common.compdoc_workflow import WORKFLOW_STATUSES, parse_workflow_date


def validate_workflow_append(instance, payload):
    """Allow identical history or one appended current workflow event."""

    imported = payload.get("status_flow") or []
    if any(not _valid_event(event) for event in imported):
        return "Workflow events require a supported status and valid date."
    if instance is None:
        return None
    existing = instance.status_flow or []
    if not existing:
        return None
    if imported == existing:
        return None
    if imported[:-1] == existing and len(imported) == len(existing) + 1:
        return None
    return "Existing workflow history cannot be edited or removed by an import."


def _valid_event(event):
    return (
        isinstance(event, dict)
        and event.get("status") in WORKFLOW_STATUSES
        and parse_workflow_date(event.get("date")) is not None
    )
