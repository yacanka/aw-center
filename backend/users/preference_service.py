"""Fresh, partial preference writes; appearance reset never touches content."""

import copy

from django.db.models import F
from django.utils import timezone

from awcenter.database_errors import retry_content_write
from .models import UserPreferences


APPEARANCE_FIELDS = ("theme", "has_particles", "items_per_page", "compact_view")


def update_user_preferences(user, values):
    def write():
        preferences, _ = UserPreferences.objects.get_or_create(user=user)
        UserPreferences.objects.filter(pk=preferences.pk).update(
            **values, version=F("version") + 1, updated_at=timezone.now())
        preferences.refresh_from_db()
        return preferences
    return retry_content_write(write, conflict_code="PREFERENCE_VERSION_CONFLICT")


def mutate_extra_settings(user, transform):
    """The transform returns field updates from a fresh extra-settings dictionary."""
    def write():
        preferences, _ = UserPreferences.objects.get_or_create(user=user)
        extra = copy.deepcopy(preferences.extra_settings) if isinstance(preferences.extra_settings, dict) else {}
        updates = transform(extra)
        changed = UserPreferences.objects.filter(pk=preferences.pk, version=preferences.version).update(
            **updates, version=F("version") + 1, updated_at=timezone.now())
        if not changed:
            return None
        preferences.refresh_from_db()
        return preferences
    return retry_content_write(write, conflict_code="PREFERENCE_VERSION_CONFLICT")


def reset_appearance(user):
    def reset(extra):
        extra.pop("watcher", None)
        defaults = {name: UserPreferences._meta.get_field(name).get_default() for name in APPEARANCE_FIELDS}
        return {**defaults, "extra_settings": extra}
    return mutate_extra_settings(user, reset)
