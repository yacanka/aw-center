"""Validate that a DCC preview still represents current Compliance Documents."""

import hashlib

from .compdoc_bridge import (
    build_bundle,
    canonical_json,
    document_sort_key,
    normalize_document_ids,
    require_model_view_permission,
    resolve_compdoc_model,
)
from .compdoc_preview_revision import read_source_snapshot
from .document_snapshot import DccSnapshotError


def validate_compdoc_preview_current(user, job):
    """Lock linked records and reject confirmation of a stale or invalid bundle."""

    document_ids = normalize_document_ids(job.parameters.get("compdoc_ids") or [])
    if not document_ids:
        return
    project_slug = str(job.parameters.get("compdoc_project") or "")
    _project, model = resolve_compdoc_model(project_slug)
    require_model_view_permission(user, model)
    snapshot = read_source_snapshot(job)
    stored_bundle = snapshot.get("compliance_documents") or {}
    validate_stored_bundle(stored_bundle, project_slug, document_ids)
    current_bundle = build_bundle(project_slug, model, locked_documents(model, document_ids))
    if rendered_bundle_fingerprint(current_bundle) != rendered_bundle_fingerprint(stored_bundle):
        raise source_changed_error()


def validate_stored_bundle(bundle, project_slug, document_ids):
    """Verify the input's internal CompDoc lineage before comparing current state."""

    documents = bundle.get("documents") or []
    stored_ids = normalize_document_ids([item.get("id") for item in documents])
    fingerprint = hashlib.sha256(canonical_json(documents)).hexdigest()
    valid = all(
        (
            bundle.get("project_slug") == project_slug,
            stored_ids == document_ids,
            bundle.get("fingerprint") == fingerprint,
        )
    )
    if not valid:
        raise DccSnapshotError(
            "The preview's compliance document snapshot is invalid.",
            "DCC_COMPDOC_SNAPSHOT_INVALID",
            409,
        )


def locked_documents(model, document_ids):
    """Return every selected current record under a confirmation transaction lock."""

    documents = list(model.objects.select_for_update().filter(pk__in=document_ids))
    if len(documents) != len(document_ids):
        raise DccSnapshotError(
            "One or more selected compliance documents no longer exist.",
            "DCC_COMPDOC_NOT_FOUND",
            404,
        )
    return sorted(documents, key=document_sort_key)


def rendered_bundle_fingerprint(bundle):
    """Digest only values rendered into the DCC, excluding history metadata."""

    excluded = {"source_history_id", "source_history_at"}
    documents = [
        {key: value for key, value in item.items() if key not in excluded}
        for item in bundle.get("documents") or []
    ]
    return hashlib.sha256(canonical_json(documents)).hexdigest()


def source_changed_error():
    """Return the stable conflict raised when a reviewed source advanced."""

    return DccSnapshotError(
        "A compliance document changed after this preview was created.",
        "DCC_COMPDOC_SOURCE_CHANGED",
        409,
    )
