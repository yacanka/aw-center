"""Durable, credential-free JIRA draft publication enqueue boundary."""

import json

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from jobs.services import (
    IdempotencyConflict,
    create_job,
    find_idempotent_job,
    require_idempotency_key,
)

from .access_policy import PUBLISHER, require_resource_role
from .issue_draft_contracts import DraftStateConflict, validate_version
from .issue_draft_models import JiraIssueDraftStatus
from .issue_draft_services import lock_draft, record_event

JOB_KIND = "dcc.publish_jira_draft"


def enqueue_draft_publication(
    actor,
    draft_id,
    expected_version,
    idempotency_key,
    *,
    reconcile=False,
    request_id="",
):
    """Reserve a fenced draft version and enqueue one provider-side effect."""

    key = require_idempotency_key(idempotency_key)
    existing = find_idempotent_job(actor, JOB_KIND, key)
    if existing:
        verify_replay(existing, draft_id, expected_version, reconcile)
        with transaction.atomic():
            draft = lock_draft(draft_id)
            require_resource_role(actor, draft, PUBLISHER)
            verify_job_projects(existing, draft)
        return existing, False

    with transaction.atomic():
        draft = lock_draft(draft_id)
        require_resource_role(actor, draft, PUBLISHER)
        validate_version(draft.version, expected_version)
        validate_enqueue_state(draft, reconcile)
        project_ids = sorted(draft.projects.values_list("pk", flat=True))
        draft.status = JiraIssueDraftStatus.PUBLISHING
        draft.publish_started_at = timezone.now()
        draft.last_error_code = ""
        draft.last_error_message = ""
        draft.version += 1
        draft.save()
        parameters = build_parameters(draft, expected_version, project_ids, reconcile)
        job, created = create_job(
            actor,
            JOB_KIND,
            f"Publish JIRA draft {draft.id}",
            parameters,
            publication_input(parameters),
            key,
            request_id,
            source_job=draft.source_job,
            reconcile_on_lease_loss=True,
        )
        if not created:
            raise IdempotencyConflict()
        draft.publication_job = job
        draft.save(update_fields=["publication_job", "updated_at"])
        record_event(
            draft,
            actor,
            "publication_queued",
            {"job_id": str(job.id), "mode": parameters["mode"]},
        )
    return job, True


def validate_enqueue_state(draft, reconcile):
    if reconcile:
        if draft.status != JiraIssueDraftStatus.RECONCILIATION_REQUIRED:
            raise DraftStateConflict()
        return
    if draft.status not in {JiraIssueDraftStatus.APPROVED, JiraIssueDraftStatus.FAILED}:
        raise DraftStateConflict()
    if not draft.approved_at:
        raise DraftStateConflict()


def build_parameters(draft, request_version, project_ids, reconcile):
    return {
        "draft_id": str(draft.id),
        "request_version": int(request_version),
        "fence_version": int(draft.version),
        "mode": "reconcile" if reconcile else "publish",
        "project_ids": [int(project_id) for project_id in project_ids],
    }


def publication_input(parameters):
    content = json.dumps(parameters, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return ContentFile(content, name="jira-draft-publication.json")


def verify_replay(existing, draft_id, expected_version, reconcile):
    expected = {
        "draft_id": str(draft_id),
        "request_version": int(expected_version),
        "mode": "reconcile" if reconcile else "publish",
    }
    if any(existing.parameters.get(key) != value for key, value in expected.items()):
        raise IdempotencyConflict()


def verify_job_projects(job, draft):
    current = sorted(draft.projects.values_list("pk", flat=True))
    if job.parameters.get("project_ids") != current:
        raise IdempotencyConflict()
