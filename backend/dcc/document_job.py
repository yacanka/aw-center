"""Render immutable DCC snapshots as verified private DOCX job artifacts."""

import json
import zipfile

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult
from jobs.worker import update_progress
from projects.registry import UnknownProjectDefinitionError, get_project_definition

from .services.template_resolver import DccTemplateResolutionError, resolve_dcc_template_path


def execute_dcc_document_creation(job):
    """Render a stored credential-free JIRA snapshot into a DCC document."""

    input_path = materialize_job_input(job)
    output_path = temporary_output(".docx")
    result_ready = False
    try:
        snapshot = load_snapshot(input_path)
        update_progress(job.id, 30, "JIRA snapshot verified.")
        render_snapshot(snapshot, output_path)
        validate_docx(output_path)
        update_progress(job.id, 90, "DCC document verified.")
        result_ready = True
        return build_result(snapshot, output_path)
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def load_snapshot(path):
    """Load and validate the versioned JSON rendering contract."""

    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JobExecutionFailure("The DCC source snapshot is invalid.", "DCC_SNAPSHOT_INVALID") from error
    required = {"schema_version", "issue_key", "project_slug", "output_name", "placeholders"}
    if snapshot.get("schema_version") != 1 or not required.issubset(snapshot):
        raise JobExecutionFailure("The DCC source snapshot is unsupported.", "DCC_SNAPSHOT_INVALID")
    if not isinstance(snapshot["placeholders"], dict):
        raise JobExecutionFailure("The DCC source snapshot is invalid.", "DCC_SNAPSHOT_INVALID")
    return snapshot


def render_snapshot(snapshot, output_path):
    """Render one allowlisted project template without using persisted credentials."""

    try:
        from docxtpl import DocxTemplate
        document = create_template_document(snapshot, DocxTemplate)
        render_document(document, snapshot, output_path)
    except (ImportError, OSError, DccTemplateResolutionError) as error:
        raise JobExecutionFailure(
            "The configured DCC template is unavailable.", "DCC_TEMPLATE_UNAVAILABLE", True
        ) from error
    except UnknownProjectDefinitionError as error:
        raise JobExecutionFailure("The DCC project is no longer available.", "DCC_PROJECT_INVALID") from error
    except Exception as error:
        raise JobExecutionFailure(
            "The DCC template could not render the captured source.", "DCC_RENDER_FAILED"
        ) from error


def create_template_document(snapshot, template_class):
    """Create one allowlisted project template instance."""

    project = get_project_definition(snapshot["project_slug"])
    return template_class(resolve_dcc_template_path(project))


def render_document(document, snapshot, output_path):
    """Render template fields and save the DCC document."""

    document.render(snapshot["placeholders"])
    document.save(output_path)


def validate_docx(path):
    """Require a non-empty valid OOXML ZIP artifact before publishing it."""

    if not path.exists() or not zipfile.is_zipfile(path):
        raise JobExecutionFailure("DCC rendering produced an invalid document.", "DCC_OUTPUT_INVALID")
    try:
        with zipfile.ZipFile(path) as archive:
            if "word/document.xml" not in archive.namelist():
                raise JobExecutionFailure(
                    "DCC rendering produced an invalid document.", "DCC_OUTPUT_INVALID"
                )
    except (OSError, zipfile.BadZipFile) as error:
        raise JobExecutionFailure(
            "DCC rendering produced an invalid document.", "DCC_OUTPUT_INVALID"
        ) from error


def build_result(snapshot, output_path):
    """Return safe result metadata for Job Center and download APIs."""

    summary = {
        "type": "dcc_document",
        "issue_key": snapshot["issue_key"],
        "project": snapshot.get("project_label", ""),
    }
    return JobExecutionResult(
        output_path, snapshot["output_name"], "DCC document created.", summary
    )
