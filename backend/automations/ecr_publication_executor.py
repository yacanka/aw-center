"""Marker-idempotent executor for approved ECR-to-JIRA publication."""

import hashlib
import json
import secrets
import tempfile
from pathlib import Path
from types import SimpleNamespace

from rest_framework.exceptions import PermissionDenied

from integrations.jira.contracts import JiraDraftPreflightBlocked, validate_issue_key
from integrations.jira.failures import create_result_is_uncertain
from integrations.jira.publisher import build_create_fields
from integrations.jira.sessions import (
    JiraSessionError,
    jira_connector_for,
    require_jira_session,
)
from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import (
    JobExecutionFailure,
    JobExecutionResult,
    JobExecutionUncertain,
)

from .ecr_publication_state import (
    complete_ecr_publication,
    confirm_attachment,
    confirm_parent,
    confirm_subtask,
    fail_ecr_publication,
    normalized_state,
    validate_ecr_publication_fence,
)
from .ecr_contracts import ecr_parent_description
from .models import EcrWorkflowStatus


def execute_ecr_jira_publication(job):
    """Publish one frozen ECR plan or reconcile its deterministic markers."""

    input_path = None
    output_path = temporary_output(".json")
    result_ready = False
    try:
        workflow = validate_worker_authorization(job)
        if workflow.status == EcrWorkflowStatus.PUBLISHED:
            result = receipt_result(workflow, output_path)
            result_ready = True
            return result
        try:
            input_path = materialize_job_input(job)
            validate_job_input(input_path, job.parameters)
        except JobExecutionFailure as error:
            fail_ecr_publication(job, error.code, str(error))
            raise
        client = resolve_connector(job)
        if job.parameters.get("mode") == "reconcile":
            workflow = reconcile_markers(job, workflow, client)
        else:
            workflow = publish_missing_operations(job, workflow, client)
        result = receipt_result(workflow, output_path)
        result_ready = True
        return result
    finally:
        if input_path:
            input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def validate_worker_authorization(job):
    try:
        return validate_ecr_publication_fence(job)
    except PermissionDenied as error:
        message = "The publisher role is no longer available for every ECR project."
        fail_ecr_publication(job, "DCC_PROJECT_ROLE_REQUIRED", message)
        raise JobExecutionFailure(
            message,
            "DCC_PROJECT_ROLE_REQUIRED",
            retryable=False,
        ) from error


def validate_job_input(path, parameters):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JobExecutionFailure(
            "The ECR publication input is invalid.",
            "ECR_PUBLICATION_INPUT_INVALID",
            retryable=False,
        ) from error
    if payload != parameters:
        raise JobExecutionFailure(
            "The ECR publication input does not match its reservation.",
            "ECR_PUBLICATION_INPUT_INVALID",
            retryable=False,
        )


def resolve_connector(job):
    try:
        return jira_connector_for(job.owner)
    except JiraSessionError as error:
        message = "Reconnect JIRA before publishing this ECR."
        fail_ecr_publication(job, "JIRA_RECONNECT_REQUIRED", message)
        raise JobExecutionFailure(
            message,
            "JIRA_RECONNECT_REQUIRED",
            retryable=False,
        ) from error


def publish_missing_operations(job, workflow, client):
    workflow = ensure_parent_issue(job, workflow, client)
    workflow = ensure_pdf_attachment(job, workflow, client)
    workflow = ensure_subtasks(job, workflow, client)
    return complete_ecr_publication(job)


def ensure_parent_issue(job, workflow, client):
    state = normalized_state(workflow)
    if state["parent_confirmed"] and workflow.jira_issue_key:
        return workflow
    ensure_session_active(job)
    try:
        existing = client.find_issue_by_label(workflow.marker_label)
    except Exception as error:
        fail_safe(
            job,
            "ECR_JIRA_MARKER_LOOKUP_FAILED",
            "JIRA publication marker lookup failed.",
            error,
        )
    if existing:
        issue_key = safe_provider_key(job, getattr(existing, "key", ""), "parent")
        return confirm_parent(job, issue_key)
    ensure_session_active(job)
    try:
        fields = build_create_fields(
            parent_draft(workflow),
            client,
            category_label="aw-center-ecr",
        )
    except JiraDraftPreflightBlocked as error:
        fail_safe(
            job,
            "ECR_JIRA_PREFLIGHT_BLOCKED",
            "Complete the required JIRA fields before publishing this ECR.",
            error,
        )
    except Exception as error:
        fail_safe(
            job,
            "ECR_JIRA_PREFLIGHT_UNAVAILABLE",
            "JIRA create requirements could not be inspected.",
            error,
        )
    ensure_session_active(job)
    try:
        issue = client.create_issue(fields)
        issue_key = validate_issue_key(getattr(issue, "key", ""))
    except Exception as error:
        provider_write_failed(job, "parent", error)
    return confirm_parent(job, issue_key)


def ensure_pdf_attachment(job, workflow, client):
    state = normalized_state(workflow)
    if state["attachment_confirmed"]:
        return workflow
    filename = attachment_filename(workflow)
    ensure_session_active(job)
    try:
        existing = client.find_attachment_by_filename(
            workflow.jira_issue_key,
            filename,
        )
    except Exception as error:
        fail_safe(
            job,
            "ECR_JIRA_ATTACHMENT_LOOKUP_FAILED",
            "The ECR attachment marker could not be inspected.",
            error,
        )
    if existing:
        return confirm_attachment(job)
    source_path = materialize_ecr_source(job, workflow)
    try:
        ensure_session_active(job)
        try:
            client.set_issue(workflow.jira_issue_key)
            with source_path.open("rb") as source:
                client.add_attachment(source, filename=filename)
        except Exception as error:
            provider_write_failed(job, "attachment", error)
    finally:
        source_path.unlink(missing_ok=True)
    return confirm_attachment(job)


def ensure_subtasks(job, workflow, client):
    for index, subtask in enumerate(workflow.selected_subtasks or ()):
        state = normalized_state(workflow)
        if str(index) in state["subtask_keys"]:
            continue
        marker = subtask_marker(workflow, index)
        ensure_session_active(job)
        try:
            existing = client.find_issue_by_label(marker)
        except Exception as error:
            fail_safe(
                job,
                "ECR_JIRA_SUBTASK_LOOKUP_FAILED",
                "A JIRA subtask marker could not be inspected.",
                error,
            )
        if existing:
            issue_key = safe_provider_key(
                job,
                getattr(existing, "key", ""),
                f"subtask:{index}",
            )
            workflow = confirm_subtask(job, index, issue_key)
            continue
        fields = build_subtask_fields(client, workflow, subtask, marker)
        ensure_session_active(job)
        try:
            issue = client.create_issue(fields)
            issue_key = validate_issue_key(getattr(issue, "key", ""))
        except Exception as error:
            provider_write_failed(job, f"subtask:{index}", error)
        workflow = confirm_subtask(job, index, issue_key)
    return workflow


def reconcile_markers(job, workflow, client):
    """Inspect every marker without issuing a provider write."""

    try:
        ensure_session_active(job)
        parent = client.find_issue_by_label(workflow.marker_label)
        if not parent:
            reconciliation_not_found(job)
        workflow = confirm_parent(
            job,
            safe_provider_key(job, getattr(parent, "key", ""), "parent"),
        )
        ensure_session_active(job)
        attachment = client.find_attachment_by_filename(
            workflow.jira_issue_key,
            attachment_filename(workflow),
        )
        if not attachment:
            reconciliation_not_found(job)
        workflow = confirm_attachment(job)
        for index, _subtask in enumerate(workflow.selected_subtasks or ()):
            ensure_session_active(job)
            existing = client.find_issue_by_label(subtask_marker(workflow, index))
            if not existing:
                reconciliation_not_found(job)
            workflow = confirm_subtask(
                job,
                index,
                safe_provider_key(
                    job,
                    getattr(existing, "key", ""),
                    f"subtask:{index}",
                ),
            )
    except (JobExecutionFailure, JobExecutionUncertain):
        raise
    except Exception as error:
        message = "JIRA marker reconciliation could not be completed."
        fail_ecr_publication(
            job,
            "ECR_RECONCILIATION_LOOKUP_FAILED",
            message,
            uncertain_operation="unknown",
        )
        raise JobExecutionUncertain(message) from error
    return complete_ecr_publication(job)


def reconciliation_not_found(job):
    message = "No confirmed JIRA marker was found for every pending operation."
    fail_ecr_publication(job, "ECR_RECONCILIATION_NOT_FOUND", message)
    raise JobExecutionFailure(
        message,
        "ECR_RECONCILIATION_NOT_FOUND",
        retryable=False,
    )


def parent_draft(workflow):
    return SimpleNamespace(
        project_key=workflow.project_key,
        summary=workflow.snapshot["title"],
        description=ecr_parent_description(workflow.snapshot),
        extra_fields=workflow.extra_fields,
        marker_label=workflow.marker_label,
    )

def build_subtask_fields(client, workflow, subtask, marker):
    client.set_issue(workflow.jira_issue_key)
    fields = client.build_subtask_fields(
        summary=subtask["summary"],
        description=subtask.get("description", ""),
        assignee=subtask.get("assignee") or None,
        duedate=subtask.get("due_date") or None,
        extra_fields={"labels": [marker, "aw-center-ecr-subtask"]},
    )
    if subtask.get("priority"):
        fields["priority"] = {"name": subtask["priority"]}
    return fields


def attachment_filename(workflow):
    return f"{workflow.marker_label}.pdf"


def subtask_marker(workflow, index):
    return f"{workflow.marker_label}-s{index + 1:02d}"


def materialize_ecr_source(job, workflow):
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    digest = hashlib.sha256()
    try:
        with workflow.source_pdf.open("rb") as source, temporary:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                temporary.write(chunk)
                digest.update(chunk)
    except Exception as error:
        Path(temporary.name).unlink(missing_ok=True)
        fail_safe(
            job,
            "ECR_SOURCE_UNAVAILABLE",
            "The private ECR source PDF is unavailable.",
            error,
        )
    if not secrets.compare_digest(digest.hexdigest(), workflow.source_sha256):
        Path(temporary.name).unlink(missing_ok=True)
        fail_safe(
            job,
            "ECR_SOURCE_INTEGRITY_FAILED",
            "The private ECR source PDF failed integrity verification.",
        )
    return Path(temporary.name)


def ensure_session_active(job):
    """Stop between provider operations when the ephemeral credential expires."""

    try:
        require_jira_session(job.owner)
    except JiraSessionError as error:
        message = "Reconnect JIRA before publishing this ECR."
        fail_ecr_publication(job, "JIRA_RECONNECT_REQUIRED", message)
        raise JobExecutionFailure(
            message,
            "JIRA_RECONNECT_REQUIRED",
            retryable=False,
        ) from error


def safe_provider_key(job, value, operation):
    try:
        return validate_issue_key(value)
    except Exception as error:
        message = "JIRA returned an invalid issue identifier."
        fail_ecr_publication(
            job,
            "ECR_JIRA_IDENTIFIER_INVALID",
            message,
            uncertain_operation=operation,
        )
        raise JobExecutionUncertain(message) from error


def provider_write_failed(job, operation, error):
    uncertain = create_result_is_uncertain(error)
    code = (
        "ECR_JIRA_RECONCILIATION_REQUIRED"
        if uncertain
        else "ECR_JIRA_WRITE_REJECTED"
    )
    message = (
        "JIRA may have committed the operation; reconcile its marker."
        if uncertain
        else "JIRA rejected the ECR publication operation."
    )
    fail_ecr_publication(
        job,
        code,
        message,
        uncertain_operation=operation if uncertain else "",
    )
    if uncertain:
        raise JobExecutionUncertain(message) from error
    raise JobExecutionFailure(message, code, retryable=False) from error


def fail_safe(job, code, message, cause=None):
    fail_ecr_publication(job, code, message)
    error = JobExecutionFailure(message, code, retryable=False)
    if cause is not None:
        raise error from cause
    raise error


def receipt_result(workflow, output_path):
    state = normalized_state(workflow)
    payload = {
        "jira_issue_key": workflow.jira_issue_key,
        "attachment_confirmed": bool(state["attachment_confirmed"]),
        "subtasks_confirmed": len(state["subtask_keys"]),
    }
    output_path.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    return JobExecutionResult(
        output_path,
        "ecr-jira-publication-receipt.json",
        "ECR publication confirmed.",
        {"type": "ecr_jira_publication", **payload},
    )
