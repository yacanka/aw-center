"""Explainable notification-event detection for compliance documents."""

from datetime import datetime, time, timedelta

from django.utils import timezone

DUE_SOON_DAYS = 7
EVENT_OPTIONS = (
    {"value": "overdue", "label": "Overdue delivery"},
    {"value": "due_soon", "label": "Delivery due within 7 days"},
    {"value": "revision_available", "label": "New DocProof revision"},
)
EVENT_KEYS = {option["value"] for option in EVENT_OPTIONS}


def detect_events(document, profile, today=None):
    """Return active notification events and their stable evidence values."""

    current_day = today or timezone.localdate()
    events = {}
    target = document.ubm_target_date
    if document.status == "to_be_issued" and target:
        days = (target - current_day).days
        if days < 0:
            events["overdue"] = target.isoformat()
        elif days <= DUE_SOON_DAYS:
            events["due_soon"] = target.isoformat()
    issue = getattr(profile, "docproof_issue", "")
    if getattr(profile, "docproof_status", "") == "revision_available" and issue:
        events["revision_available"] = issue
    return events


def event_states(document, profile, today=None):
    """Describe why each supported event is or is not currently applicable."""

    current_day = today or timezone.localdate()
    active_events = detect_events(document, profile, current_day)
    return [
        {
            **option,
            "applicable": option["value"] in active_events,
            "detail": _event_detail(option["value"], document, profile, current_day),
        }
        for option in EVENT_OPTIONS
    ]


def event_started_at(document, profile, event_type):
    """Return the first known instant at which an active event became applicable."""

    if event_type == "revision_available":
        return getattr(profile, "docproof_issue_detected_at", None)
    target = document.ubm_target_date
    if not target:
        return None
    start_day = target + timedelta(days=1) if event_type == "overdue" else target - timedelta(days=7)
    return timezone.make_aware(datetime.combine(start_day, time.min))


def _event_detail(event_type, document, profile, current_day):
    if event_type == "revision_available":
        return _revision_detail(profile)
    return _delivery_detail(event_type, document, current_day)


def _delivery_detail(event_type, document, current_day):
    target = document.ubm_target_date
    if document.status != "to_be_issued":
        return "Available only while the document status is To be Issued."
    if not target:
        return "Add a target date to evaluate this delivery alert."
    days = (target - current_day).days
    if event_type == "overdue":
        return _overdue_detail(target, days)
    return _due_soon_detail(target, days)


def _overdue_detail(target, days):
    formatted = target.strftime("%d.%m.%Y")
    if days < 0:
        return f"Target {formatted} is overdue by {abs(days)} day(s)."
    return f"Target {formatted} has not passed yet."


def _due_soon_detail(target, days):
    formatted = target.strftime("%d.%m.%Y")
    if days < 0:
        return f"Target {formatted} is already overdue; use the overdue alert."
    if days == 0:
        return f"Target {formatted} is due today."
    if days <= DUE_SOON_DAYS:
        return f"Target {formatted} is due in {days} day(s)."
    return f"Target {formatted} is more than {DUE_SOON_DAYS} days away."


def _revision_detail(profile):
    status = getattr(profile, "docproof_status", "never_checked")
    issue = getattr(profile, "docproof_issue", "")
    if status == "revision_available" and issue:
        return f"DocProof issue {issue} is newer than the recorded document issue."
    if status == "current":
        return "The recorded document issue matches the latest DocProof issue."
    if status == "unavailable":
        return "The latest DocProof check was unavailable; retry the check first."
    return "Check DocProof to determine whether a newer revision exists."
