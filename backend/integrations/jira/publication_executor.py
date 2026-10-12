"""Worker adapter for fenced, marker-idempotent JIRA draft publication."""

import json

from rest_framework.exceptions import PermissionDenied

from integrations.jira.contracts import JiraDraftPreflightBlocked, validate_issue_key
from integrations.jira.failures import create_result_is_uncertain
from integrations.jira.publisher import build_create_fields, find_existing_issue
from integrations.jira.sessions import (
    JiraSessionError,
    jira_connector_for,
    require_jira_session,
)
from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult

from .issue_draft_models import JiraIssueDraftStatus
from .issue_draft_publication_state import (
    complete_publication,
    fail_publication,
    validate_publication_fence,
)


def execute_jira_draft_publication(job):
    """Publish or explicitly reconcile one credential-free durable job."""

    input_path = None
    output_path = temporary_output(".json")
    result_ready = False
    try:
        draft = validate_worker_authorization(job)
        if draft.status == JiraIssueDraftStatus.PUBLISHED:
            result = receipt_result(
                job,
                draft.jira_issue_key,
                output_path,
                marker_reused=True,
            )
            result_ready = True
            return result
        try:
            input_path = materialize_job_input(job)
            validate_input(input_path, job.parameters)
        except JobExecutionFailure as error:
            fail_publication(job, error.code, str(error))
            raise
        client = resolve_connector(job)
        existing_key = find_marker(job, draft, client)
        if existing_key:
            complete_publication(
                job,
                existing_key,
                reconciled=job.parameters.get("mode") == "reconcile",
            )
            result = receipt_result(job, existing_key, output_path, marker_reused=True)
            result_ready = True
            return result
        if job.parameters.get("mode") == "reconcile":
            fail_and_raise(
                job,
                "JIRA_RECONCILIATION_NOT_FOUND",
                "No JIRA issue was found for the publication marker.",
            )
        fields = prepare_fields(job, draft, client)
        issue_key = create_provider_issue(job, client, fields)
        complete_publication(job, issue_key)
        result = receipt_result(job, issue_key, output_path, marker_reused=False)
        result_ready = True
        return result
    finally:
        if input_path:
            input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def validate_input(path, parameters):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JobExecutionFailure(
            "The JIRA publication input is invalid.",
            "JIRA_PUBLICATION_INPUT_INVALID",
            retryable=False,
        ) from error
    if payload != parameters:
        raise JobExecutionFailure(
            "The JIRA publication input does not match its reservation.",
            "JIRA_PUBLICATION_INPUT_INVALID",
            retryable=False,
        )


def validate_worker_authorization(job):
    try:
        return validate_publication_fence(job)
    except PermissionDenied as error:
        fail_publication(
            job,
            "DCC_PROJECT_ROLE_REQUIRED",
            "The publisher role is no longer available for every draft project.",
        )
        raise JobExecutionFailure(
            "The publisher role is no longer available for every draft project.",
            "DCC_PROJECT_ROLE_REQUIRED",
            retryable=False,
        ) from error


def resolve_connector(job):
    try:
        return jira_connector_for(job.owner)
    except JiraSessionError as error:
        fail_publication(
            job,
            "JIRA_RECONNECT_REQUIRED",
            "Reconnect JIRA before publishing this draft.",
        )
        raise JobExecutionFailure(
            "Reconnect JIRA before publishing this draft.",
            "JIRA_RECONNECT_REQUIRED",
            retryable=False,
        ) from error


def find_marker(job, draft, client):
    ensure_session_active(job)
    try:
        return find_existing_issue(draft, client)
    except Exception as error:
        if job.parameters.get("mode") == "reconcile":
            message = "JIRA publication marker reconciliation could not be completed."
            fail_publication(
                job,
                "JIRA_RECONCILIATION_LOOKUP_FAILED",
                message,
                reconciliation_required=True,
            )
            raise JobExecutionFailure(
                message,
                "JIRA_RECONCILIATION_LOOKUP_FAILED",
                retryable=False,
            ) from error
        fail_and_raise(
            job,
            "JIRA_MARKER_LOOKUP_FAILED",
            "JIRA publication marker lookup failed.",
            cause=error,
        )


def prepare_fields(job, draft, client):
    ensure_session_active(job)
    try:
        return build_create_fields(draft, client)
    except JiraDraftPreflightBlocked as error:
        fail_and_raise(
            job,
            "JIRA_DRAFT_PREFLIGHT_BLOCKED",
            "Complete the required JIRA fields before publication.",
            cause=error,
        )
    except Exception as error:
        fail_and_raise(
            job,
            "JIRA_DRAFT_PREFLIGHT_UNAVAILABLE",
            "JIRA create requirements could not be inspected.",
            cause=error,
        )


def create_provider_issue(job, client, fields):
    ensure_session_active(job)
    try:
        issue = client.create_issue(fields)
        return validate_issue_key(issue.key)
    except Exception as error:
        uncertain = create_result_is_uncertain(error)
        code = "JIRA_PUBLICATION_RECONCILIATION_REQUIRED" if uncertain else "JIRA_DRAFT_PUBLISH_FAILED"
        message = (
            "JIRA may have created the issue; reconcile the publication marker."
            if uncertain
            else "JIRA rejected issue publication."
        )
        fail_publication(job, code, message, reconciliation_required=uncertain)
        raise JobExecutionFailure(message, code, retryable=False) from error


def fail_and_raise(job, code, message, cause=None):
    fail_publication(job, code, message)
    error = JobExecutionFailure(message, code, retryable=False)
    if cause is not None:
        raise error from cause
    raise error


def ensure_session_active(job):
    """Revalidate ephemeral JIRA state immediately before each provider call."""

    try:
        require_jira_session(job.owner)
    except JiraSessionError as error:
        message = "Reconnect JIRA before publishing this draft."
        fail_publication(job, "JIRA_RECONNECT_REQUIRED", message)
        raise JobExecutionFailure(
            message,
            "JIRA_RECONNECT_REQUIRED",
            retryable=False,
        ) from error


def receipt_result(job, issue_key, output_path, marker_reused):
    payload = {
        "draft_id": job.parameters["draft_id"],
        "jira_issue_key": issue_key,
        "marker_reused": bool(marker_reused),
    }
    output_path.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    return JobExecutionResult(
        output_path,
        "jira-publication-receipt.json",
        "JIRA draft publication confirmed.",
        {"type": "jira_draft_publication", **payload},
    )
