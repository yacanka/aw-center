"""Versioned project policy for CompDoc notification cadence and recipients."""

from copy import deepcopy
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from common.compdoc_notification_events import EVENT_OPTIONS, event_started_at
from common.compdoc_tracking_models import CompDocNotificationPolicy
from common.models import Titles

MAX_POLICY_HISTORY = 8


class PolicyVersionConflict(Exception):
    """Indicate that another operator activated a newer policy revision."""


def default_event_rules():
    """Return safe rules matching the existing one-delivery behavior."""

    retry_hours = min(
        720, max(1, (settings.COMPDOC_NOTIFICATION_RETRY_SECONDS + 3599) // 3600)
    )
    rule = {
        "reminder_interval_hours": 0,
        "failure_retry_hours": retry_hours,
        "primary_titles": [],
        "escalation_titles": [],
        "escalate_after_hours": 0,
    }
    return {option["value"]: deepcopy(rule) for option in EVENT_OPTIONS}


def active_policy(project_slug):
    """Return the active immutable policy revision for a project."""

    return CompDocNotificationPolicy.objects.filter(
        project_slug=project_slug, is_active=True
    ).first()


def policy_context(project_slug):
    """Return normalized active rules and version with one database lookup."""

    policy = active_policy(project_slug)
    return {
        "rules": deepcopy(policy.event_rules) if policy else default_event_rules(),
        "version": policy.version if policy else 0,
    }


def policy_payload(project_slug, can_manage=False):
    """Build the project policy, role catalogue, and bounded revision history."""

    policy = active_policy(project_slug)
    revisions = CompDocNotificationPolicy.objects.filter(project_slug=project_slug)
    return {
        "project": project_slug,
        "configured": policy is not None,
        "version": policy.version if policy else 0,
        "rules": deepcopy(policy.event_rules) if policy else default_event_rules(),
        "role_options": [{"value": value, "label": label} for value, label in Titles.choices],
        "event_options": list(EVENT_OPTIONS),
        "can_manage": can_manage,
        "change_note": policy.change_note if policy else "",
        "updated_by": policy.updated_by_username if policy else "",
        "updated_at": policy.created_at if policy else None,
        "history": [_revision_payload(item) for item in revisions[:MAX_POLICY_HISTORY]],
    }


@transaction.atomic
def save_policy(project_slug, rules, change_note, expected_version, user):
    """Activate a new policy revision while retaining immutable history."""

    revisions = CompDocNotificationPolicy.objects.select_for_update().filter(
        project_slug=project_slug
    )
    latest_version = revisions.aggregate(value=Max("version"))["value"] or 0
    if latest_version != expected_version:
        raise PolicyVersionConflict
    version = latest_version + 1
    revisions.filter(is_active=True).update(is_active=False)
    return CompDocNotificationPolicy.objects.create(
        project_slug=project_slug,
        version=version,
        event_rules=deepcopy(rules),
        change_note=change_note,
        updated_by=user,
        updated_by_username=user.get_username(),
    )


def event_rule(project_slug, event_type):
    """Return the active rule and policy version for one event."""

    context = policy_context(project_slug)
    return deepcopy(context["rules"][event_type]), context["version"]


def partition_contacts(
    project_slug, event_type, contacts, document, profile, now=None, context=None
):
    """Split current ATA contacts into primary and active escalation recipients."""

    active_context = context or policy_context(project_slug)
    rule = deepcopy(active_context["rules"][event_type])
    primary = _contacts_with_titles(contacts, rule["primary_titles"])
    escalation = _escalation_contacts(rule, contacts, document, profile, event_type, now)
    primary_ids = {contact["id"] for contact in primary}
    escalation = [contact for contact in escalation if contact["id"] not in primary_ids]
    if not primary and escalation:
        primary, escalation = escalation, []
    return {
        "primary": primary,
        "escalation": escalation,
        "rule": rule,
        "version": active_context["version"],
    }


def delivery_event_states(project_slug, states, contacts, document, profile):
    """Add exact current recipient-tier counts to explainable event states."""

    context = policy_context(project_slug)
    return [
        _delivery_state(
            state,
            partition_contacts(
                project_slug,
                state["value"],
                contacts,
                document,
                profile,
                context=context,
            ),
        )
        for state in states
    ]


def delivery_occurrence(rule, started_at, now=None):
    """Return a stable deduplication slot for an event reminder interval."""

    interval = int(rule["reminder_interval_hours"])
    if interval <= 0 or not started_at:
        return "once"
    elapsed = max(0, ((now or timezone.now()) - started_at).total_seconds())
    return f"{interval}h-{int(elapsed // (interval * 3600))}"


def retry_due(log, rule, now=None):
    """Return whether an event-specific failed-delivery cooldown elapsed."""

    if log.status != "failed":
        return False
    cooldown = timedelta(hours=int(rule["failure_retry_hours"]))
    return log.updated_at <= (now or timezone.now()) - cooldown


def _escalation_contacts(rule, contacts, document, profile, event_type, now):
    titles = rule["escalation_titles"]
    started_at = event_started_at(document, profile, event_type)
    if not titles or not started_at:
        return []
    elapsed = (now or timezone.now()) - started_at
    if elapsed < timedelta(hours=int(rule["escalate_after_hours"])):
        return []
    return _contacts_with_titles(contacts, titles)


def _contacts_with_titles(contacts, titles):
    if not titles:
        return list(contacts)
    allowed = set(titles)
    return [contact for contact in contacts if contact["title"] in allowed]


def _revision_payload(policy):
    return {
        "version": policy.version,
        "change_note": policy.change_note,
        "updated_by": policy.updated_by_username,
        "created_at": policy.created_at,
        "is_active": policy.is_active,
    }


def _delivery_state(state, plan):
    return {
        **state,
        "recipient_count": len(plan["primary"]) + len(plan["escalation"]),
        "primary_recipient_count": len(plan["primary"]),
        "escalation_recipient_count": len(plan["escalation"]),
        "policy_version": plan["version"],
    }
