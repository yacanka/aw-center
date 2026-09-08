"""Fenced permanent deletion for archived compliance documents."""

from django.db import transaction
from django.db.models.deletion import ProtectedError

from .models import (
    ComplianceDocument,
    CoverPageNumberAllocation,
    DocumentPurgeAudit,
)


class DocumentPurgeError(Exception):
    """Report a rejected compliance-document purge without leaking internals."""


@transaction.atomic
def purge_document(*, document_id, expected_version, operator, reason):
    """Permanently delete one archived document while retaining audit evidence."""

    if expected_version < 1:
        raise DocumentPurgeError("Expected version must be positive.")
    if not operator.is_active or not operator.is_superuser:
        raise DocumentPurgeError("Only an active superuser may purge compliance documents.")

    reason = str(reason or "").strip()
    if not 3 <= len(reason) <= 255:
        raise DocumentPurgeError("Reason must contain between 3 and 255 characters.")

    try:
        document = (
            ComplianceDocument.objects.select_for_update()
            .select_related("project")
            .get(pk=document_id)
        )
    except ComplianceDocument.DoesNotExist as error:
        raise DocumentPurgeError("The compliance document does not exist.") from error

    if not document.is_archived:
        raise DocumentPurgeError("Archive the compliance document before purging it.")
    if document.version != expected_version:
        raise DocumentPurgeError("The compliance document version changed before purge.")

    project = document.project
    document_version = document.version
    document._history_user = operator
    document._change_reason = reason[:100]

    # Number allocation is durable integration evidence. Retain it while removing
    # the protected link that would otherwise prevent the explicit purge.
    CoverPageNumberAllocation.objects.select_for_update().filter(
        document=document
    ).update(document=None)
    try:
        document.delete()
    except ProtectedError as error:
        raise DocumentPurgeError(
            "The compliance document is referenced by protected evidence."
        ) from error

    return DocumentPurgeAudit.objects.create(
        document_id=document_id,
        project=project,
        document_version=document_version,
        purged_by=operator,
        purged_by_username=operator.get_username(),
        reason=reason,
    )
