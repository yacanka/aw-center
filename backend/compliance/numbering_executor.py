"""Durable executor for Numarator-backed compliance document creation."""

import json
import re
from types import SimpleNamespace

from django.db import transaction
from rest_framework.exceptions import ValidationError

from integrations.numarator.client import (
    NumaratorClient,
    NumaratorConfigurationError,
    NumaratorConflictError,
    NumaratorRejectedError,
    NumaratorTemporaryError,
    credential_fingerprint,
    is_configured,
)
from jobs.artifacts import temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult, JobExecutionUncertain
from jobs.execution import current_execution_lease, lock_active_execution, update_progress
from orgs.access_policy import has_project_role
from orgs.models import ProjectRoleAssignment

from .models import CoverPage, CoverPageNumberAllocation
from .serializers import ComplianceDocumentSerializer

CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def execute_cover_page_number_allocation(job):
    """Allocate, bind, and consume one cover page number without duplicate writes."""

    allocation = _load_authorized_allocation(job)
    client = _client_for(allocation)
    try:
        if allocation.remote_id is None:
            update_progress(job.id, 15, "Requesting a cover page number.")
            generated = client.generate_number(
                format_code=allocation.format_code,
                context_data=allocation.context_data,
                metadata={
                    "source": "aw-center",
                    "project": allocation.project.slug,
                    "allocation_id": str(allocation.id),
                },
                external_reference=str(allocation.id),
                idempotency_key=f"awc-cover-page:{allocation.id}",
            )
            _record_remote_allocation(job, allocation.id, generated)
        allocation.refresh_from_db()
        if allocation.document_id is None:
            update_progress(job.id, 55, "Saving the compliance document.")
            _bind_document(job, allocation.id)
        allocation.refresh_from_db()
        if allocation.remote_status != "used":
            update_progress(job.id, 80, "Confirming number usage.")
            used = client.mark_used(allocation.remote_id)
            _complete_allocation(job, allocation.id, used)
        else:
            _complete_existing_used_allocation(job, allocation.id)
    except NumaratorTemporaryError as error:
        _record_error(job, allocation.id, "NUMARATOR_TEMPORARY_FAILURE", str(error))
        raise JobExecutionFailure(
            "Numarator is temporarily unavailable.",
            "NUMARATOR_TEMPORARY_FAILURE",
            True,
        ) from error
    except NumaratorRejectedError as error:
        _record_error(job, allocation.id, "NUMARATOR_REQUEST_REJECTED", str(error))
        raise JobExecutionFailure(
            "Numarator rejected the cover page number request.",
            "NUMARATOR_REQUEST_REJECTED",
        ) from error
    except NumaratorConflictError as error:
        _record_reconciliation(job, allocation.id, str(error))
        raise JobExecutionUncertain(
            "Confirm the Numarator allocation before continuing."
        ) from error
    finally:
        client.close()

    allocation.refresh_from_db()
    output_path = temporary_output(".json")
    output_path.write_text(
        json.dumps(
            {
                "allocation_id": str(allocation.id),
                "document_id": str(allocation.document_id),
                "cover_page_id": str(allocation.cover_page_id),
                "number": allocation.remote_number,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return JobExecutionResult(
        output_path,
        "cover-page-number.json",
        "Cover page number created and assigned.",
        summary={
            "allocation_id": str(allocation.id),
            "document_id": str(allocation.document_id),
            "number": allocation.remote_number,
        },
    )


def _load_authorized_allocation(job):
    try:
        allocation = CoverPageNumberAllocation.objects.select_related(
            "project", "actor", "current_job"
        ).get(pk=job.parameters.get("allocation_id"))
    except (CoverPageNumberAllocation.DoesNotExist, ValueError, TypeError) as error:
        raise JobExecutionFailure(
            "The cover page allocation input is invalid.", "NUMARATOR_ALLOCATION_INVALID"
        ) from error
    if allocation.current_job_id != job.id:
        raise JobExecutionFailure(
            "This cover page allocation attempt is stale.", "NUMARATOR_ALLOCATION_STALE"
        )
    if not allocation.actor.is_active or not has_project_role(
        allocation.actor,
        allocation.project,
        ProjectRoleAssignment.Domain.COMPLIANCE,
        ProjectRoleAssignment.Role.EDITOR,
    ):
        raise JobExecutionFailure(
            "The requester can no longer edit this project.", "PROJECT_ROLE_REQUIRED"
        )
    return allocation


def _client_for(allocation):
    if (
        not is_configured(allocation.project.slug, require_credential=True)
        or credential_fingerprint() != allocation.credential_fingerprint
    ):
        raise JobExecutionFailure(
            "The Numarator credential changed before this allocation completed.",
            "NUMARATOR_CREDENTIAL_CHANGED",
        )
    try:
        return NumaratorClient()
    except NumaratorConfigurationError as error:
        raise JobExecutionFailure(
            "Numarator is not configured.", "NUMARATOR_NOT_CONFIGURED"
        ) from error


def _lock(job, allocation_id):
    lease = current_execution_lease(job.id)
    lock_active_execution(lease, allow_cancel_requested=True)
    allocation = CoverPageNumberAllocation.objects.select_for_update().select_related(
        "project", "actor", "document", "cover_page"
    ).get(pk=allocation_id)
    if allocation.current_job_id != job.id:
        raise JobExecutionFailure(
            "This cover page allocation attempt is stale.", "NUMARATOR_ALLOCATION_STALE"
        )
    return allocation


@transaction.atomic
def _record_remote_allocation(job, allocation_id, generated):
    allocation = _lock(job, allocation_id)
    if generated.format_code.casefold() != allocation.format_code.casefold():
        raise NumaratorConflictError("Numarator returned a different format.")
    if (
        not generated.number
        or generated.number != generated.number.strip()
        or len(generated.number) > 32
        or CONTROL_CHARACTERS.search(generated.number)
    ):
        raise NumaratorConflictError("The generated number does not fit the cover page contract.")
    if allocation.remote_id is not None and (
        allocation.remote_id != generated.remote_id
        or allocation.remote_number != generated.number
    ):
        raise NumaratorConflictError("Numarator returned a different allocation.")
    allocation.remote_id = generated.remote_id
    allocation.remote_number = generated.number
    allocation.remote_status = generated.status
    allocation.remote_request_id = generated.request_id
    allocation.status = CoverPageNumberAllocation.Status.ALLOCATED
    allocation.error_code = ""
    allocation.error_detail = ""
    allocation.save()


@transaction.atomic
def _bind_document(job, allocation_id):
    allocation = _lock(job, allocation_id)
    if allocation.document_id:
        return allocation.document
    if CoverPage.objects.filter(
        project=allocation.project,
        number=allocation.remote_number,
    ).exists():
        raise NumaratorConflictError("The generated number already exists in this project.")
    payload = dict(allocation.document_snapshot)
    payload["cover_page"] = {
        **payload.get("cover_page", {}),
        "number": allocation.remote_number,
    }
    serializer = ComplianceDocumentSerializer(
        data=payload,
        context={
            "project": allocation.project,
            "request": SimpleNamespace(user=allocation.actor),
        },
    )
    try:
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
    except ValidationError as error:
        raise JobExecutionFailure(
            "The compliance document is no longer valid.",
            "COMPDOC_ALLOCATION_INPUT_INVALID",
        ) from error
    allocation.document = document
    allocation.cover_page = document.cover_page
    allocation.status = CoverPageNumberAllocation.Status.USE_PENDING
    allocation.save()
    return document


@transaction.atomic
def _complete_allocation(job, allocation_id, used):
    allocation = _lock(job, allocation_id)
    if (
        used.remote_id != allocation.remote_id
        or used.number != allocation.remote_number
        or used.format_code.casefold() != allocation.format_code.casefold()
        or used.status != "used"
    ):
        raise NumaratorConflictError("Numarator did not confirm the expected number usage.")
    allocation.remote_status = "used"
    allocation.remote_request_id = used.request_id or allocation.remote_request_id
    allocation.status = CoverPageNumberAllocation.Status.COMPLETED
    allocation.error_code = ""
    allocation.error_detail = ""
    allocation.save()


@transaction.atomic
def _complete_existing_used_allocation(job, allocation_id):
    allocation = _lock(job, allocation_id)
    if not allocation.document_id or not allocation.cover_page_id:
        raise NumaratorConflictError("The used number has no verified local document.")
    allocation.status = CoverPageNumberAllocation.Status.COMPLETED
    allocation.error_code = ""
    allocation.error_detail = ""
    allocation.save()


@transaction.atomic
def _record_error(job, allocation_id, code, detail):
    allocation = _lock(job, allocation_id)
    allocation.error_code = code
    allocation.error_detail = str(detail)[:500]
    allocation.save(update_fields=["error_code", "error_detail", "updated_at"])


@transaction.atomic
def _record_reconciliation(job, allocation_id, detail):
    allocation = _lock(job, allocation_id)
    allocation.status = CoverPageNumberAllocation.Status.RECONCILIATION_REQUIRED
    allocation.error_code = "RECONCILIATION_REQUIRED"
    allocation.error_detail = str(detail)[:500]
    allocation.save(update_fields=["status", "error_code", "error_detail", "updated_at"])
