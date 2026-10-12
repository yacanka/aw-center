"""Persistence helpers for user-owned document-analysis questions."""

from uuid import uuid4

from django.db.models import F
from django.utils import timezone

from awcenter.database_errors import retry_content_write
from .models import DocumentAnalysisUserContent
from word.analysis_contracts import (
    AnalysisChecklistError,
    MAX_CUSTOM_CHECKS,
    normalize_custom_check,
    normalize_custom_checks,
)


def get_custom_checks(user):
    """Return the authenticated user's validated custom analysis checks."""

    content = DocumentAnalysisUserContent.objects.filter(user=user).first()
    return normalize_custom_checks(content.checks if content else [])


def create_custom_check(user, question):
    """Append one validated custom check under a locked user profile."""

    check = normalize_custom_check({"id": uuid4(), "question": question})
    def write():
        content, _ = DocumentAnalysisUserContent.objects.get_or_create(user=user)
        checks = normalize_custom_checks(content.checks)
        if len(checks) >= MAX_CUSTOM_CHECKS:
            raise AnalysisChecklistError(f"Save at most {MAX_CUSTOM_CHECKS} custom questions.")
        if any(item["question"].casefold() == check["question"].casefold() for item in checks):
            raise AnalysisChecklistError("This question is already saved.")
        return check if save_checks(content, [*checks, check]) else None
    return retry_content_write(write, conflict_code="ANALYSIS_CONTENT_VERSION_CONFLICT")


def delete_custom_check(user, identifier):
    """Delete one custom check from a locked user profile."""

    def write():
        content = DocumentAnalysisUserContent.objects.filter(user=user).first()
        if content is None:
            return False
        checks = normalize_custom_checks(content.checks)
        remaining = [item for item in checks if item["id"] != str(identifier)]
        if len(remaining) == len(checks):
            return False
        return True if save_checks(content, remaining) else None
    return retry_content_write(write, conflict_code="ANALYSIS_CONTENT_VERSION_CONFLICT")


def save_checks(content, checks):
    """Persist a validated checklist through its dedicated profile field."""

    return DocumentAnalysisUserContent.objects.filter(pk=content.pk, version=content.version).update(
        checks=checks, version=F("version") + 1, updated_at=timezone.now())
