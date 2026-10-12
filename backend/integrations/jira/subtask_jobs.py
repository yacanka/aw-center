"""Durable enqueue and explicit-resume boundary for JIRA subtask batches."""

import hashlib
import json

from django.core.files.base import ContentFile
from django.db import transaction
from rest_framework.exceptions import ValidationError

from integrations.jira.sessions import require_jira_session
from jobs.artifacts import materialize_job_input
from jobs.models import Job, JobStatus
from jobs.services import create_job, require_idempotency_key

from .access_policy import OPERATOR, enabled_projects_by_ids, require_projects_role

JOB_KIND = "dcc.create_jira_subtasks"


def enqueue_subtask_batch(actor, issue_key, projects, items, idempotency_key, request_id=""):
    """Persist an immutable, credential-free subtask plan."""

    key = require_idempotency_key(idempotency_key)
    operation_id = operation_identifier(actor.pk, key)
    payload = {
        "schema_version": 1,
        "operation_id": operation_id,
        "issue_key": issue_key,
        "project_ids": sorted(project.pk for project in projects),
        "items": serialize_items(items),
    }
    parameters = job_parameters(payload, mode="create")
    return create_job(
        actor,
        JOB_KIND,
        f"Create {len(items)} JIRA subtasks for {issue_key}",
        parameters,
        json_input(payload),
        key,
        request_id,
        reconcile_on_lease_loss=True,
    )


@transaction.atomic
def enqueue_subtask_resume(actor, source_job_id, idempotency_key, request_id=""):
    """Create a new fenced attempt that reuses the original provider markers."""

    key = require_idempotency_key(idempotency_key)
    source = Job.objects.select_for_update().filter(
        pk=source_job_id,
        owner=actor,
        kind=JOB_KIND,
    ).first()
    if source is None:
        raise ValidationError({"job": "The subtask job was not found."})
    if source.status not in {JobStatus.FAILED, JobStatus.RECONCILIATION_REQUIRED}:
        raise ValidationError({"job": "Only a failed or uncertain subtask job can be resumed."})
    projects = enabled_projects_by_ids(source.parameters.get("project_ids", ()))
    require_projects_role(actor, projects, OPERATOR)
    require_jira_session(actor)
    input_path = materialize_job_input(source)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError({"job": "The original subtask plan is unavailable."}) from error
    finally:
        input_path.unlink(missing_ok=True)
    parameters = job_parameters(payload, mode="resume", resume_of=source.id)
    return create_job(
        actor,
        JOB_KIND,
        f"Resume JIRA subtasks for {payload['issue_key']}",
        parameters,
        json_input(payload),
        key,
        request_id,
        source_job=source,
        reconcile_on_lease_loss=True,
    )


def operation_identifier(owner_id, idempotency_key):
    digest = hashlib.sha256(f"{owner_id}:{idempotency_key}".encode("utf-8")).hexdigest()
    return digest[:24]


def serialize_items(items):
    return [
        {
            "summary": item["summary"],
            "description": item.get("description", ""),
            "assignee": item.get("assignee", ""),
            "due_date": item["due_date"].isoformat() if item.get("due_date") else None,
            "fields": item.get("fields", {}),
        }
        for item in items
    ]


def job_parameters(payload, *, mode, resume_of=None):
    return {
        "schema_version": payload["schema_version"],
        "operation_id": payload["operation_id"],
        "issue_key": payload["issue_key"],
        "project_ids": payload["project_ids"],
        "item_count": len(payload["items"]),
        "mode": mode,
        "resume_of": str(resume_of) if resume_of else None,
    }


def json_input(payload):
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return ContentFile(content.encode("utf-8"), name="jira-subtask-batch.json")
