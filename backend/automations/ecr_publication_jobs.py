"""Credential-free durable enqueue boundary for ECR publication."""

import json

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from integrations.jira.sessions import require_jira_session
from jobs.persistence import (
    IdempotencyConflict,
    create_job,
    find_idempotent_job,
    require_idempotency_key,
)

from .ecr_access import PUBLISHER, require_ecr_role
from .ecr_contracts import EcrStateConflict, validate_ecr_version
from .ecr_services import (
    lock_ecr_workflow,
    record_ecr_event,
)
from .models import EcrWorkflowStatus

JOB_KIND = "automations.publish_ecr_jira"


def enqueue_ecr_publication(
    actor,
    workflow_id,
    expected_version,
    idempotency_key,
    *,
    action,
    request_id="",
):
    """Reserve one approved snapshot for a fenced external-write job."""

    key = require_idempotency_key(idempotency_key)
    existing = find_idempotent_job(actor, JOB_KIND, key)
    if existing:
        with transaction.atomic():
            workflow = lock_ecr_workflow(workflow_id, actor)
            require_ecr_role(actor, workflow, PUBLISHER)
            verify_publication_replay(
                existing,
                workflow,
                expected_version,
                action,
            )
        return workflow, existing, False

    with transaction.atomic():
        workflow = lock_ecr_workflow(workflow_id, actor)
        require_ecr_role(actor, workflow, PUBLISHER)
        # A same-key request may have been waiting on this workflow lock while
        # the first request committed.  Recheck under the lock before treating
        # the now-incremented workflow version as a conflicting mutation.
        existing = find_idempotent_job(actor, JOB_KIND, key)
        if existing:
            verify_publication_replay(
                existing,
                workflow,
                expected_version,
                action,
            )
            return workflow, existing, False
        # Verify availability without persisting or copying the credential.
        require_jira_session(actor)
        validate_ecr_version(workflow.version, expected_version)
        mode = validate_publication_action(workflow, action)
        prepare_publication_state(workflow, mode)
        workflow.status = EcrWorkflowStatus.PUBLISHING
        workflow.publish_started_at = timezone.now()
        workflow.last_error_code = ""
        workflow.last_error_message = ""
        workflow.version += 1
        workflow.save()
        parameters = build_publication_parameters(
            workflow,
            expected_version,
            action,
            mode,
        )
        job, created = create_job(
            actor,
            JOB_KIND,
            f"Publish ECR {workflow.snapshot.get('ecr_number', '')}"[:160],
            parameters,
            publication_input(parameters),
            key,
            request_id,
            reconcile_on_lease_loss=True,
        )
        if not created:
            raise IdempotencyConflict()
        workflow.publication_job = job
        workflow.save(update_fields=["publication_job", "updated_at"])
        record_ecr_event(
            workflow,
            actor,
            "publication_queued",
            details={"job_id": str(job.id), "mode": mode},
        )
        return workflow, job, True


def validate_publication_action(workflow, action):
    if action == "publish":
        if workflow.status != EcrWorkflowStatus.APPROVED:
            raise EcrStateConflict()
        return "publish"
    if action != "resume":
        raise EcrStateConflict()
    if workflow.status == EcrWorkflowStatus.RECONCILIATION_REQUIRED:
        return "reconcile"
    if workflow.status in {
        EcrWorkflowStatus.FAILED,
        EcrWorkflowStatus.CANCELLED,
    }:
        return "resume"
    raise EcrStateConflict()


def prepare_publication_state(workflow, mode):
    state = dict(workflow.publication_state or {})
    if mode == "publish":
        state = {
            "parent_confirmed": False,
            "attachment_confirmed": False,
            "subtask_keys": {},
            "uncertain_operation": "",
        }
    elif mode == "resume":
        state["uncertain_operation"] = ""
    workflow.publication_state = state


def build_publication_parameters(workflow, request_version, action, mode):
    return {
        "workflow_id": str(workflow.id),
        "request_version": int(request_version),
        "fence_version": int(workflow.version),
        "action": action,
        "mode": mode,
        "project_slugs": sorted(workflow.projects.values_list("slug", flat=True)),
    }


def publication_input(parameters):
    content = json.dumps(parameters, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return ContentFile(content, name="ecr-publication.json")


def verify_publication_replay(job, workflow, expected_version, action):
    expected = {
        "workflow_id": str(workflow.id),
        "request_version": int(expected_version),
        "action": action,
    }
    if any(job.parameters.get(key) != value for key, value in expected.items()):
        raise IdempotencyConflict()
    if workflow.publication_job_id != job.id:
        raise IdempotencyConflict()
