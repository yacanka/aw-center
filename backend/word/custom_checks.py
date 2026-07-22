"""Persistence helpers for user-owned document-analysis questions."""

from uuid import uuid4

from django.db import transaction

from users.models import UserPreferences
from word.analysis_contracts import (
    AnalysisChecklistError,
    MAX_CUSTOM_CHECKS,
    normalize_custom_check,
    normalize_custom_checks,
)


def get_custom_checks(user):
    """Return the authenticated user's validated custom analysis checks."""

    preferences, _ = UserPreferences.objects.get_or_create(user=user)
    return normalize_custom_checks(preferences.document_analysis_checks)


@transaction.atomic
def create_custom_check(user, question):
    """Append one validated custom check under a locked user profile."""

    preferences = locked_preferences(user)
    checks = normalize_custom_checks(preferences.document_analysis_checks)
    if len(checks) >= MAX_CUSTOM_CHECKS:
        raise AnalysisChecklistError(f"Save at most {MAX_CUSTOM_CHECKS} custom questions.")
    check = normalize_custom_check({"id": uuid4(), "question": question})
    if any(item["question"].casefold() == check["question"].casefold() for item in checks):
        raise AnalysisChecklistError("This question is already saved.")
    save_checks(preferences, [*checks, check])
    return check


@transaction.atomic
def delete_custom_check(user, identifier):
    """Delete one custom check from a locked user profile."""

    preferences = locked_preferences(user)
    checks = normalize_custom_checks(preferences.document_analysis_checks)
    remaining = [item for item in checks if item["id"] != str(identifier)]
    if len(remaining) == len(checks):
        return False
    save_checks(preferences, remaining)
    return True


def locked_preferences(user):
    """Return one existing profile row under a transaction lock."""

    preferences, _ = UserPreferences.objects.get_or_create(user=user)
    return UserPreferences.objects.select_for_update().get(pk=preferences.pk)


def save_checks(preferences, checks):
    """Persist a validated checklist through its dedicated profile field."""

    preferences.document_analysis_checks = checks
    preferences.save(update_fields=["document_analysis_checks", "updated_at"])
