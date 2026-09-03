"""Marker-idempotent worker executor for bounded JIRA subtask batches."""

import json

from integrations.jira.contracts import validate_issue_key
from integrations.jira.field_values import encode_value
from integrations.jira.failures import create_result_is_uncertain
from integrations.jira.sessions import JiraSessionError, jira_connector_for, require_jira_session
from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult, JobExecutionUncertain
from jobs.execution import cancellation_requested, update_progress

from .access_policy import OPERATOR, enabled_projects_by_ids, require_projects_role
from .subtask_jobs import JOB_KIND


def execute_jira_subtask_batch(job):
    """Create missing marker-bound subtasks and emit a private receipt."""

    input_path = materialize_job_input(job)
    output_path = temporary_output(".json")
    result_ready = False
    try:
        payload = load_payload(input_path, job)
        validate_authorization(job, payload)
        client = resolve_connector(job)
        encoded_fields = prepare_extra_fields(client, payload)
        created_keys = []
        reused_keys = []
        total = len(payload["items"])
        for index, item in enumerate(payload["items"], start=1):
            if cancellation_requested(job.id):
                from jobs.contracts import JobCancelled

                raise JobCancelled()
            marker = marker_label(payload["operation_id"], index)
            update_progress(job.id, progress_before(index, total), f"Checking subtask {index} of {total}.")
            existing = find_existing(job, client, marker)
            if existing:
                reused_keys.append(existing)
                continue
            fields = client.build_subtask_fields(
                item["summary"],
                item.get("description", ""),
                item.get("assignee") or None,
                item.get("due_date"),
                {**encoded_fields[index - 1], "labels": [marker, "aw-center-subtask"]},
            )
            ensure_session(job)
            try:
                issue = client.create_subtask_from_fields(fields, item.get("assignee") or None)
                created_keys.append(validate_issue_key(issue.key))
            except Exception as error:
                if create_result_is_uncertain(error):
                    raise JobExecutionUncertain(
                        f"JIRA may have created subtask {index}; resume to reconcile its marker."
                    ) from error
                raise JobExecutionFailure(
                    f"JIRA rejected subtask {index}.",
                    "JIRA_SUBTASK_CREATE_REJECTED",
                    retryable=False,
                ) from error
        receipt = {
            "type": "jira_subtask_batch",
            "issue_key": payload["issue_key"],
            "created_count": len(created_keys),
            "reused_count": len(reused_keys),
            "subtask_keys": created_keys + reused_keys,
        }
        output_path.write_text(
            json.dumps(receipt, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        result_ready = True
        return JobExecutionResult(
            output_path,
            "jira-subtask-receipt.json",
            f"Confirmed {total} JIRA subtasks.",
            receipt,
        )
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def load_payload(path, job):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JobExecutionFailure(
            "The JIRA subtask plan is invalid.",
            "JIRA_SUBTASK_INPUT_INVALID",
        ) from error
    required = {"schema_version", "operation_id", "issue_key", "project_ids", "items"}
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise JobExecutionFailure("The JIRA subtask plan is invalid.", "JIRA_SUBTASK_INPUT_INVALID")
    expected = {
        "schema_version": job.parameters.get("schema_version"),
        "operation_id": job.parameters.get("operation_id"),
        "issue_key": job.parameters.get("issue_key"),
        "project_ids": job.parameters.get("project_ids"),
        "item_count": job.parameters.get("item_count"),
    }
    actual = {
        "schema_version": payload.get("schema_version"),
        "operation_id": payload.get("operation_id"),
        "issue_key": payload.get("issue_key"),
        "project_ids": payload.get("project_ids"),
        "item_count": len(payload.get("items", ())) if isinstance(payload.get("items"), list) else -1,
    }
    if actual != expected or not 1 <= actual["item_count"] <= 100:
        raise JobExecutionFailure("The JIRA subtask plan is invalid.", "JIRA_SUBTASK_INPUT_INVALID")
    return payload


def validate_authorization(job, payload):
    try:
        projects = enabled_projects_by_ids(payload["project_ids"])
        require_projects_role(job.owner, projects, OPERATOR)
    except Exception as error:
        raise JobExecutionFailure(
            "The operator role is no longer available for every project.",
            "DCC_PROJECT_ROLE_REQUIRED",
        ) from error


def resolve_connector(job):
    try:
        client = jira_connector_for(job.owner)
        client.set_issue(job.parameters["issue_key"])
        return client
    except JiraSessionError as error:
        raise JobExecutionFailure(
            "Reconnect JIRA before creating subtasks.",
            "JIRA_RECONNECT_REQUIRED",
        ) from error


def prepare_extra_fields(client, payload):
    """Revalidate and encode the live JIRA field contract before any external write."""

    from .subtask_contracts import sanitize_subtask_fields, validate_item_field_contract

    try:
        metadata = client.get_subtask_fields()
        public_metadata = sanitize_subtask_fields(metadata)
        validate_item_field_contract(payload["items"], public_metadata)
        public_field_ids = {item["id"] for item in public_metadata}
        fields_by_id = {
            field["id"]: field
            for field in metadata
            if field.get("id") in public_field_ids
        }
        return [
            {
                key: encode_value(value, fields_by_id[key])
                for key, value in item.get("fields", {}).items()
                if value not in (None, "", [])
            }
            for item in payload["items"]
        ]
    except Exception as error:
        raise JobExecutionFailure(
            "Reload JIRA fields before creating subtasks.",
            "JIRA_SUBTASK_FIELD_CONTRACT_CHANGED",
        ) from error


def find_existing(job, client, marker):
    ensure_session(job)
    try:
        issue = client.find_issue_by_label(marker)
        return validate_issue_key(issue.key) if issue else None
    except Exception as error:
        raise JobExecutionFailure(
            "JIRA subtask marker lookup failed.",
            "JIRA_SUBTASK_MARKER_LOOKUP_FAILED",
        ) from error


def ensure_session(job):
    try:
        require_jira_session(job.owner)
    except JiraSessionError as error:
        raise JobExecutionFailure(
            "Reconnect JIRA before creating subtasks.",
            "JIRA_RECONNECT_REQUIRED",
        ) from error


def marker_label(operation_id, index):
    return f"awcenter-st-{operation_id}-{index}"


def progress_before(index, total):
    return min(95, int(((index - 1) / max(total, 1)) * 95))
