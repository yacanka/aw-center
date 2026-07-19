"""Sanitized lifecycle recording for CompDoc imports."""

import hashlib
from pathlib import Path

from django.utils import timezone

from .models import CompDocImportAudit

MAX_AUDIT_COLUMNS = 100
MAX_AUDIT_ERRORS = 100
MAX_ERROR_TEXT = 500


def start_import_audit(request, model, uploaded_file):
    """Create a processing audit before parsing a confirmed import."""

    return CompDocImportAudit.objects.create(
        project_slug=model._meta.app_label,
        source_filename=safe_filename(uploaded_file.name),
        source_size=max(int(uploaded_file.size or 0), 0),
        source_sha256=hash_uploaded_file(uploaded_file),
        imported_by=request.user,
        imported_by_username=request.user.get_username(),
        request_id=str(getattr(request, "request_id", ""))[:64],
    )


def record_import_mapping(audit, preview, total_rows):
    """Attach bounded mapping metadata to an active audit."""

    audit.header_row = preview["header_row"]
    audit.mapped_columns = bounded_mappings(preview["mapped_columns"])
    audit.unmapped_columns = bounded_values(preview["unmapped_columns"])
    audit.missing_columns = bounded_values(preview["missing_columns"])
    audit.total_rows = max(int(total_rows), 0)
    audit.save(update_fields=mapping_update_fields())


def complete_import_audit(audit, result):
    """Finalize an audit from sanitized import result counts."""

    audit.created_count = result["created_count"]
    audit.updated_count = result["updated_count"]
    audit.rejected_count = result["rejected_count"]
    audit.error_summary = result["errors"][:MAX_AUDIT_ERRORS]
    audit.status = result_status(result)
    finish_audit(audit)


def fail_import_audit(audit, code, detail):
    """Finalize an audit failure without persisting raw exception text."""

    audit.status = CompDocImportAudit.Status.FAILED
    audit.rejected_count = audit.total_rows
    audit.error_summary = [{"code": code, "detail": str(detail)[:MAX_ERROR_TEXT]}]
    finish_audit(audit)


def finish_audit(audit):
    """Persist terminal timing and lifecycle fields."""

    completed_at = timezone.now()
    audit.completed_at = completed_at
    elapsed = (completed_at - audit.started_at).total_seconds() * 1000
    audit.duration_ms = max(int(elapsed), 0)
    audit.save(update_fields=completion_update_fields())


def hash_uploaded_file(uploaded_file):
    """Return a SHA-256 digest while restoring the upload cursor."""

    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def safe_filename(filename):
    """Return only a bounded source basename for audit display."""

    return Path(str(filename)).name[:255] or "upload.xlsx"


def bounded_mappings(mappings):
    """Return bounded source-target mapping evidence."""

    return [
        {"source": str(item.get("source", ""))[:128], "target": str(item.get("target", ""))[:128]}
        for item in mappings[:MAX_AUDIT_COLUMNS]
    ]


def bounded_values(values):
    """Return bounded string evidence values."""

    return [str(value)[:128] for value in values[:MAX_AUDIT_COLUMNS]]


def result_status(result):
    """Resolve result counters into one terminal lifecycle status."""

    if not result["rejected_count"]:
        return CompDocImportAudit.Status.SUCCESS
    if result["created_count"] or result["updated_count"]:
        return CompDocImportAudit.Status.PARTIAL
    return CompDocImportAudit.Status.FAILED


def mapping_update_fields():
    """Return fields persisted after workbook preparation."""

    return [
        "header_row",
        "mapped_columns",
        "unmapped_columns",
        "missing_columns",
        "total_rows",
    ]


def completion_update_fields():
    """Return fields persisted at terminal audit completion."""

    return [
        "created_count",
        "updated_count",
        "rejected_count",
        "error_summary",
        "status",
        "completed_at",
        "duration_ms",
    ]
