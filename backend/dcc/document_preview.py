"""Build a safe DCC impact preview from one immutable JIRA snapshot."""

from jobs.artifacts import temporary_output
from jobs.contracts import JobExecutionFailure

from .document_job import render_snapshot, validate_docx
from .document_snapshot import DccSnapshotError

RECOMMENDED_FIELDS = {
    "DCC_Form_Number": "DCC form number",
    "Design_Change_Number": "design change number",
    "Design_Change_Revision": "design change revision",
    "Design_Change_Title": "design change title",
    "Responsible_AS": "responsible AS",
}


def prepare_dcc_preview(snapshot):
    """Dry-render the exact snapshot and return content-free impact metadata."""

    validate_snapshot_rendering(snapshot)
    placeholders = snapshot["placeholders"]
    missing = [label for key, label in RECOMMENDED_FIELDS.items() if not placeholders.get(key)]
    return {
        "type": "dcc_preview",
        "issue_key": snapshot["issue_key"],
        "project": snapshot.get("project_label", ""),
        "output_name": snapshot["output_name"],
        "panel_count": snapshot.get("panel_count", 0),
        "template_ready": True,
        "source_updated_at": placeholders.get("Update_Time", ""),
        "missing_recommended_fields": missing,
        "warning_count": len(missing),
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
