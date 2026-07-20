"""User decision operations for Action Center attention items."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from common.action_center_models import ActionCenterDecision

SNOOZE_DURATION = timedelta(days=1)


def filter_user_decisions(user, items):
    """Hide items dismissed or currently snoozed by one user."""

    if not items:
        return items
    item_keys = [item["id"] for item in items]
    decisions = ActionCenterDecision.objects.filter(user=user, item_key__in=item_keys)
    hidden_keys = {
        decision.item_key
        for decision in decisions
        if decision_hides_item(decision)
    }
    return [item for item in items if item["id"] not in hidden_keys]


@transaction.atomic
def record_attention_decision(user, item_key, action):
    """Persist one bounded dismiss or 24-hour snooze decision."""

    now = timezone.now()
    values = decision_values(action, now)
    decision, _ = ActionCenterDecision.objects.update_or_create(
        user=user,
        item_key=item_key,
        defaults=values,
    )
    return decision


def decision_values(action, now):
    """Return mutually exclusive terminal or temporary decision timestamps."""

    if action == "dismiss":
        return {"acknowledged_at": now, "snoozed_until": None}
    return {"acknowledged_at": None, "snoozed_until": now + SNOOZE_DURATION}


def decision_hides_item(decision):
    """Return whether a decision currently suppresses its attention item."""

    if decision.acknowledged_at:
        return True
    return bool(decision.snoozed_until and decision.snoozed_until > timezone.now())
