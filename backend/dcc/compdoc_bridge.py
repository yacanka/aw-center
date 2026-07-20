"""Capture project compliance documents for immutable DCC traceability."""

import hashlib
import json
from uuid import UUID

from django.apps import apps
from django.utils import timezone

from projects.registry import UnknownProjectDefinitionError, get_project_definition

from .compdoc_capture import captured_compdoc_values, scalar
from .document_snapshot import DccSnapshotError

MAX_COMPDOC_SELECTION = 50


def parse_compdoc_selection(payload):
    """Return a validated project slug and deterministic UUID selection."""

    raw_ids = payload.get("compdoc_ids") or []
    project_slug = str(payload.get("compdoc_project") or "").strip().lower()
    if not isinstance(raw_ids, list):
        raise bridge_error("Select compliance documents as a list.", "DCC_COMPDOC_IDS_INVALID")
    if len(raw_ids) > MAX_COMPDOC_SELECTION:
        raise bridge_error("Select at most 50 compliance documents.", "DCC_COMPDOC_LIMIT")
    document_ids = normalize_document_ids(raw_ids)
    if bool(document_ids) != bool(project_slug):
        raise bridge_error("Compliance document project and selections are both required.", "DCC_COMPDOC_SELECTION_INVALID")
    return project_slug, document_ids


def normalize_document_ids(raw_ids):
    """Normalize unique UUID values into stable ordering."""

    try:
        document_ids = [str(UUID(str(value))) for value in raw_ids]
    except (TypeError, ValueError, AttributeError) as error:
        raise bridge_error("A compliance document identifier is invalid.", "DCC_COMPDOC_ID_INVALID") from error
    if len(set(document_ids)) != len(document_ids):
        raise bridge_error("A compliance document was selected more than once.", "DCC_COMPDOC_DUPLICATE")
    return sorted(document_ids)


def attach_compliance_documents(snapshot, user, project_slug, document_ids):
    """Attach an authorized, versioned compliance register to a DCC snapshot."""

    if not document_ids:
        return snapshot
    project, model = resolve_compdoc_model(project_slug)
    validate_bridge_access(snapshot, user, project, model)
    documents = fetch_documents(model, document_ids)
    snapshot["compliance_documents"] = build_bundle(project.slug, model, documents)
    return snapshot


def resolve_compdoc_model(project_slug):
    """Resolve an enabled registry project and its concrete CompDoc model."""

    try:
        project = get_project_definition(project_slug)
        model = apps.get_model(project.slug, "CompDoc")
    except (UnknownProjectDefinitionError, LookupError) as error:
        raise bridge_error("The compliance document project is not supported.", "DCC_COMPDOC_PROJECT_INVALID") from error
    if not project.enabled or "compdocs" not in project.capabilities or model is None:
        raise bridge_error("The compliance document project is not available.", "DCC_COMPDOC_PROJECT_INVALID")
    return project, model


def validate_bridge_access(snapshot, user, project, model):
    """Require project alignment and the concrete model's view permission."""

    if snapshot.get("project_slug") != project.slug:
        raise bridge_error("Selected documents do not belong to the JIRA task project.", "DCC_COMPDOC_PROJECT_MISMATCH")
    require_model_view_permission(user, model)


def validate_compdoc_job_access(user, parameters):
    """Recheck CompDoc access when replaying or confirming a private preview."""

    document_ids = parameters.get("compdoc_ids") or []
    if not document_ids:
        return
    _project, model = resolve_compdoc_model(parameters.get("compdoc_project", ""))
    require_model_view_permission(user, model)


def require_model_view_permission(user, model):
    """Require the concrete project's CompDoc view permission."""

    permission = f"{model._meta.app_label}.view_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise bridge_error("You cannot use this project's compliance documents.", "DCC_COMPDOC_FORBIDDEN", 403)


def fetch_documents(model, document_ids):
    """Fetch every selected record or reject stale and unknown selections."""

    documents = list(model.objects.filter(pk__in=document_ids))
    if len(documents) != len(document_ids):
        raise bridge_error("One or more selected compliance documents no longer exist.", "DCC_COMPDOC_NOT_FOUND", 404)
    return sorted(documents, key=document_sort_key)


def build_bundle(project_slug, model, documents):
    """Build canonical records, source versions, and a tamper-evident digest."""

    versions = latest_history_versions(model, documents)
    records = [serialize_document(document, versions.get(str(document.pk))) for document in documents]
    fingerprint = hashlib.sha256(canonical_json(records)).hexdigest()
    return {
        "schema_version": 1,
        "project_slug": project_slug,
        "captured_at": timezone.now().isoformat(),
        "fingerprint": fingerprint,
        "documents": records,
    }


def latest_history_versions(model, documents):
    """Return the newest historical source version for each selected record."""

    document_ids = [document.pk for document in documents]
    history = model.history.model.objects.filter(id__in=document_ids).values(
        "id", "history_id", "history_date"
    ).order_by("id", "-history_date", "-history_id")
    versions = {}
    for entry in history:
        versions.setdefault(str(entry["id"]), entry)
    return versions


def serialize_document(document, version):
    """Serialize only bounded fields required by the DCC traceability register."""

    return {
        "id": str(document.pk),
        "source_history_id": version["history_id"] if version else None,
        "source_history_at": version["history_date"].isoformat() if version else "",
        **captured_compdoc_values(document),
    }


def document_sort_key(document):
    """Return deterministic register ordering independent of selection order."""

    return tuple(scalar(value).casefold() for value in (document.panel, document.ata, document.name, document.pk))


def canonical_json(value):
    """Encode a deterministic JSON payload for fingerprint calculation."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def bridge_error(message, code, response_status=400):
    """Create a safe DCC bridge validation error."""

    return DccSnapshotError(message, code, response_status)
