"""Invalidate review snapshots when document or shared cover content changes."""

from django.utils import timezone

from .models import ComplianceDocument, ReviewTask


def supersede_pending_reviews(document, user):
    ReviewTask.objects.filter(
        document=document,
        status=ReviewTask.Status.PENDING,
    ).exclude(source_version=document.version).update(
        status=ReviewTask.Status.SUPERSEDED,
        decision_note="Document changed after this review was requested.",
        decided_by=user,
        decided_by_username=user.get_username(),
        decided_at=timezone.now(),
    )


def invalidate_shared_cover_reviews(cover_page, user, *, editing_document_id=None):
    """Version every existing sibling under the caller's project/cover locks."""

    documents = ComplianceDocument.objects.select_for_update().filter(
        cover_page=cover_page,
    ).exclude(pk=editing_document_id).order_by("pk")
    for document in documents:
        document.version += 1
        document._history_user = user
        document._change_reason = "Shared cover page revision changed."
        document.save(update_fields=["version", "updated_at"])
        supersede_pending_reviews(document, user)
