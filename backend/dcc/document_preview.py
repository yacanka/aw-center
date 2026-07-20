"""Build a safe DCC impact preview from one immutable JIRA snapshot."""

from jobs.artifacts import temporary_output
from jobs.contracts import JobExecutionFailure

from .document_job import render_snapshot, validate_docx
from .document_snapshot import DccSnapshotError
from .readiness import assess_dcc_readiness

RECOMMENDED_FIELDS = {
    "DCC_Form_Number": "DCC form number",
    "Design_Change_Number": "design change number",
    "Design_Change_Revision": "design change revision",
    "Design_Change_Title": "design change title",
    "Responsible_AS": "responsible AS",
}


def prepare_dcc_preview(snapshot, recommendations=None):
    """Dry-render the exact snapshot and return content-free impact metadata."""

    validate_snapshot_rendering(snapshot)
    placeholders = snapshot["placeholders"]
    missing = [label for key, label in RECOMMENDED_FIELDS.items() if not placeholders.get(key)]
    summary = base_preview_summary(snapshot, missing)
    compliance = compliance_preview(snapshot.get("compliance_documents"))
    summary.update(compliance)
    summary.update(assess_dcc_readiness(snapshot, missing, compliance))
    summary.update(recommendations or {})
    return summary


def base_preview_summary(snapshot, missing):
    """Return JIRA and template impact fields for the confirmation screen."""

    placeholders = snapshot["placeholders"]
    return {
        "type": "dcc_preview",
        "issue_key": snapshot["issue_key"],
        "project": snapshot.get("project_label", ""),
        "output_name": snapshot["output_name"],
        "panel_count": snapshot.get("panel_count", 0),
        "template_ready": True,
        "source_updated_at": placeholders.get("Update_Time", ""),
        "missing_recommended_fields": missing,
    }


def compliance_preview(bundle):
    """Return content-free CompDoc impact metadata for explicit confirmation."""

    documents = bundle.get("documents", []) if isinstance(bundle, dict) else []
    statuses = {}
    for document in documents:
        status = document.get("status") or "unspecified"
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "compliance_document_count": len(documents),
        "compliance_document_fingerprint": bundle.get("fingerprint", "") if documents else "",
        "compliance_document_statuses": statuses,
        "compliance_documents_without_technical_reference": sum(
            not document.get("technical_documents") for document in documents
        ),
    }


def validate_snapshot_rendering(snapshot):
    """Prove the registered template can render this exact captured source."""

    output_path = temporary_output(".docx")
    try:
        render_snapshot(snapshot, output_path)
        validate_docx(output_path)
    except JobExecutionFailure as error:
        raise DccSnapshotError(str(error), error.code) from error
    finally:
        output_path.unlink(missing_ok=True)
