"""Transactional review lifecycle for feature-owned ECR workflows."""

import secrets
import uuid

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from jobs.persistence import (
    IdempotencyConflict,
    calculate_upload_sha256,
    require_idempotency_key,
)
from jobs.models import JobStatus

from .ecr_access import OPERATOR, require_ecr_projects_role, require_ecr_role
from .ecr_contracts import EcrPdfInvalid, EcrStateConflict, validate_ecr_version
from .ecr_parser import EcrPdfParseError, parse_ecr_pdf
from .models import EcrWorkflow, EcrWorkflowEvent, EcrWorkflowStatus


def create_ecr_workflow(owner, projects, upload, idempotency_key):
    """Parse, persist, and idempotently expose one private ECR review."""

    project_list = list(projects)
    require_ecr_projects_role(owner, project_list, OPERATOR)
    key = require_idempotency_key(idempotency_key)
    digest = calculate_upload_sha256(upload)
    existing = find_create_replay(owner, key)
    if existing:
        verify_create_replay(existing, digest, project_list)
        return existing, False
    try:
        snapshot = parse_ecr_pdf(upload)
    except EcrPdfParseError as error:
        raise EcrPdfInvalid() from error
    return persist_ecr_workflow(owner, project_list, upload, digest, snapshot, key)


def persist_ecr_workflow(owner, projects, upload, digest, snapshot, key):
    """Persist metadata and source while cleaning an uncommitted private file."""

    workflow = EcrWorkflow(
        id=uuid.uuid4(),
        owner=owner,
        source_sha256=digest,
        create_idempotency_key=key,
        snapshot=snapshot,
        marker_label=f"aw-ecr-{uuid.uuid4().hex}",
    )
    stored_name = ""
    try:
        with transaction.atomic():
            workflow.source_pdf.save("source.pdf", upload, save=False)
            stored_name = workflow.source_pdf.name
            workflow.save(force_insert=True)
            workflow.projects.set(projects)
            record_ecr_event(workflow, owner, "created")
        return workflow, True
    except IntegrityError:
        delete_private_source(workflow, stored_name)
        existing = find_create_replay(owner, key)
        if not existing:
            raise
        verify_create_replay(existing, digest, projects)
        return existing, False
    except Exception:
        delete_private_source(workflow, stored_name)
        raise


def delete_private_source(workflow, stored_name):
    if stored_name:
        workflow.source_pdf.storage.delete(stored_name)


def find_create_replay(owner, key):
    return EcrWorkflow.objects.filter(
        owner=owner,
        create_idempotency_key=key,
    ).first()


def verify_create_replay(workflow, digest, projects):
    require_ecr_role(workflow.owner, workflow, OPERATOR)
    expected_projects = {project.slug for project in projects}
    current_projects = set(workflow.projects.values_list("slug", flat=True))
    if not secrets.compare_digest(workflow.source_sha256, digest) or (
        current_projects != expected_projects
    ):
        raise IdempotencyConflict()


def approve_ecr_workflow(workflow_id, actor, values):
    """Freeze the reviewed JIRA task and subtask selection."""

    with transaction.atomic():
        workflow = lock_ecr_workflow(workflow_id, actor)
        require_ecr_role(actor, workflow, OPERATOR)
        validate_ecr_version(workflow.version, values["version"])
        if workflow.status != EcrWorkflowStatus.REVIEW:
            raise EcrStateConflict()
        workflow.project_key = values["project_key"]
        workflow.extra_fields = values.get("extra_fields", {})
        workflow.selected_subtasks = serialize_subtasks(values.get("subtasks", ()))
        workflow.status = EcrWorkflowStatus.APPROVED
        workflow.approved_by = actor
        workflow.approved_at = timezone.now()
        workflow.version += 1
        workflow.save()
        record_ecr_event(workflow, actor, "approved")
        return workflow


def reject_ecr_workflow(workflow_id, actor, expected_version):
    """Make an explicit review rejection terminal."""

    with transaction.atomic():
        workflow = lock_ecr_workflow(workflow_id, actor)
        require_ecr_role(actor, workflow, OPERATOR)
        validate_ecr_version(workflow.version, expected_version)
        if workflow.status != EcrWorkflowStatus.REVIEW:
            raise EcrStateConflict()
        workflow.status = EcrWorkflowStatus.REJECTED
        workflow.rejected_at = timezone.now()
        workflow.version += 1
        workflow.save()
        record_ecr_event(workflow, actor, "rejected")
        return workflow


def project_ecr_job_terminal(job):
    """Project a terminal generic job outcome at the job mutation boundary."""

    source_statuses = {
        JobStatus.CANCELLED: {EcrWorkflowStatus.PUBLISHING},
        JobStatus.FAILED: {EcrWorkflowStatus.PUBLISHING},
        JobStatus.SUCCEEDED: {EcrWorkflowStatus.PUBLISHING},
        # A child may have persisted a definite feature failure just before the
        # parent observes cancellation or lease loss.  The job's conservative
        # reconciliation outcome must win over that intermediate failure.
        JobStatus.RECONCILIATION_REQUIRED: {
            EcrWorkflowStatus.PUBLISHING,
            EcrWorkflowStatus.FAILED,
        },
    }.get(job.status)
    if not source_statuses:
        return None
    with transaction.atomic():
        workflow = (
            EcrWorkflow.objects.select_for_update()
            .filter(
                publication_job=job,
                status__in=source_statuses,
            )
            .first()
        )
        if workflow is None:
            return None
        if job.status == JobStatus.CANCELLED:
            synchronize_terminal(
                workflow,
                EcrWorkflowStatus.CANCELLED,
                "ECR_PUBLICATION_CANCELLED",
                "Publication was cancelled before provider dispatch.",
            )
        elif job.status == JobStatus.RECONCILIATION_REQUIRED:
            state = dict(workflow.publication_state or {})
            state["uncertain_operation"] = state.get("uncertain_operation") or "unknown"
            workflow.publication_state = state
            synchronize_terminal(
                workflow,
                EcrWorkflowStatus.RECONCILIATION_REQUIRED,
                "ECR_RECONCILIATION_REQUIRED",
                "Confirm the JIRA marker state before publishing again.",
            )
        elif job.status == JobStatus.FAILED:
            synchronize_terminal(
                workflow,
                EcrWorkflowStatus.FAILED,
                job.error_code or "ECR_PUBLICATION_FAILED",
                job.message or "JIRA publication failed.",
            )
        elif job.status == JobStatus.SUCCEEDED:
            state = dict(workflow.publication_state or {})
            state["uncertain_operation"] = state.get("uncertain_operation") or "unknown"
            workflow.publication_state = state
            synchronize_terminal(
                workflow,
                EcrWorkflowStatus.RECONCILIATION_REQUIRED,
                "ECR_PUBLICATION_STATE_INCOMPLETE",
                "Confirm the JIRA marker state before publishing again.",
            )
        return workflow


def synchronize_terminal(workflow, status, code, message):
    workflow.status = status
    workflow.last_error_code = str(code)[:64]
    workflow.last_error_message = str(message)[:500]
    workflow.version += 1
    workflow.save()
    record_ecr_event(
        workflow,
        workflow.owner,
        "reconciliation_required"
        if status == EcrWorkflowStatus.RECONCILIATION_REQUIRED
        else "publication_cancelled"
        if status == EcrWorkflowStatus.CANCELLED
        else "publication_failed",
        code=code,
    )


def lock_ecr_workflow(workflow_id, owner=None):
    # Keep the row lock on the workflow itself.  Joining the nullable
    # publication job here makes PostgreSQL reject FOR UPDATE on the outer
    # join, while callers only need publication_job_id inside the transaction.
    queryset = EcrWorkflow.objects.select_for_update().prefetch_related("projects")
    if owner is not None:
        queryset = queryset.filter(owner=owner)
    try:
        return queryset.get(pk=workflow_id)
    except (EcrWorkflow.DoesNotExist, TypeError, ValueError) as error:
        raise Http404 from error


def serialize_subtasks(values):
    result = []
    for value in values:
        due_date = value.get("due_date")
        result.append(
            {
                "summary": value["summary"],
                "description": value.get("description", ""),
                "assignee": value.get("assignee", ""),
                "priority": value.get("priority", ""),
                "due_date": due_date.isoformat() if due_date else None,
            }
        )
    return result


def record_ecr_event(workflow, actor, event_type, *, code="", details=None):
    return EcrWorkflowEvent.objects.create(
        workflow=workflow,
        actor=actor,
        event_type=event_type,
        version=workflow.version,
        code=str(code)[:64],
        details=details or {},
    )
