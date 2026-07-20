"""User-specific visibility decisions for cross-workflow attention items."""

from django.conf import settings
from django.db import models


class ActionCenterDecision(models.Model):
    """Persist one user's dismissal or temporary snooze for an attention item."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="action_center_decisions",
    )
    item_key = models.CharField(max_length=100)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "item_key"],
                name="common_unique_action_decision",
            )
        ]
        indexes = [models.Index(fields=["user", "snoozed_until"])]
