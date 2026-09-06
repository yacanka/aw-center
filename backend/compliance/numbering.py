"""Durable orchestration for Numarator-backed cover page creation."""

import hashlib
import json

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from integrations.numarator.client import credential_fingerprint, is_configured, project_format_code
from jobs.models import JobStatus
from jobs.serializers import JobSerializer
from jobs.services import create_job

from .models import CoverPageNumberAllocation
from .serializers import ComplianceDocumentSerializer
from .services import VersionConflict


class NumaratorUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "NUMARATOR_NOT_CONFIGURED"
    default_detail = "Numarator is not configured for this project."


class AllocationConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "NUMARATOR_ALLOCATION_CONFLICT"
    default_detail = "This allocation request was already used with different input."


class CoverPageAllocationRequestSerializer(serializers.Serializer):
    client_operation_id = serializers.UUIDField()
    document = serializers.JSONField()

    def validate_document(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Use a document object.")
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 32 * 1024:
            raise serializers.ValidationError("The document payload is too large.")
        cover_page = value.get("cover_page")
        if not isinstance(cover_page, dict):
            raise serializers.ValidationError({"cover_page": "Use a cover page object."})
        candidate = json.loads(encoded)
        candidate["cover_page"] = {**cover_page, "number": "NUMARATOR-PENDING"}
        document_serializer = ComplianceDocumentSerializer(
            data=candidate,
            context=self.context,
        )
        document_serializer.is_valid(raise_exception=True)
        return _json_snapshot(document_serializer.validated_data)


def create_allocation(*, project, actor, client_operation_id, document, request_id=""):
    """Persist one idempotent allocation intent and ensure it has a durable job."""

    if not is_configured(project.slug):
        raise NumaratorUnavailable()
    format_code = project_format_code(project.slug)
    context_data = {"project": project.slug}
    canonical_request = {
        "document": document,
        "format_code": format_code,
        "context_data": context_data,
    }
    request_hash = hashlib.sha256(
        json.dumps(
            canonical_request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    try:
        with transaction.atomic():
            allocation = CoverPageNumberAllocation.objects.create(
                project=project,
                actor=actor,
                client_operation_id=client_operation_id,
                request_hash=request_hash,
                document_snapshot=document,
                format_code=format_code,
                context_data=context_data,
                credential_fingerprint=credential_fingerprint(),
            )
    except IntegrityError:
        allocation = CoverPageNumberAllocation.objects.get(
            project=project,
            actor=actor,
            client_operation_id=client_operation_id,
        )
        if allocation.request_hash != request_hash:
            raise AllocationConflict()
    ensure_allocation_job(allocation, request_id=request_id)
    allocation.refresh_from_db()
    return allocation


def resume_allocation(*, allocation, expected_version, request_id=""):
    """Queue another attempt for a failed allocation without changing remote identity."""

    with transaction.atomic():
        locked = CoverPageNumberAllocation.objects.select_for_update().get(pk=allocation.pk)
        if locked.version != expected_version:
            raise VersionConflict("The allocation changed after you opened it.")
        if locked.status == CoverPageNumberAllocation.Status.COMPLETED:
            return locked
        if locked.current_job_id and locked.current_job.status in {
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        }:
            return locked
        locked.version += 1
        locked.current_job = None
        locked.error_code = ""
        locked.error_detail = ""
        locked.save(
            update_fields=["version", "current_job", "error_code", "error_detail", "updated_at"]
        )
        ensure_allocation_job(locked, request_id=request_id)
    locked.refresh_from_db()
    return locked


def ensure_allocation_job(allocation, *, request_id=""):
    """Create the allocation's current durable job if one is not already linked."""

    with transaction.atomic():
        locked = CoverPageNumberAllocation.objects.select_for_update().get(pk=allocation.pk)
        if (
            locked.current_job_id
            or locked.status == CoverPageNumberAllocation.Status.COMPLETED
        ):
            return locked.current_job
        payload = json.dumps(
            {"schema_version": 1, "allocation_id": str(locked.id)},
            separators=(",", ":"),
        ).encode("utf-8")
        job, _created = create_job(
            owner=locked.actor,
            kind="compliance.allocate_cover_page_number",
            title=f"Create cover page number · {locked.project.slug}"[:160],
            parameters={"allocation_id": str(locked.id)},
            uploaded_file=ContentFile(payload, name="cover-page-number.json"),
            idempotency_key=f"numarator:{locked.id}:v{locked.version}",
            request_id=request_id,
            reconcile_on_lease_loss=True,
        )
        locked.current_job = job
        locked.save(update_fields=["current_job", "updated_at"])
        return job


def allocation_payload(allocation, request=None):
    """Serialize safe allocation state with its current job and created document."""

    document = None
    if allocation.document_id:
        document = ComplianceDocumentSerializer(
            allocation.document,
            context={"request": request, "project": allocation.project},
        ).data
    return {
        "id": str(allocation.id),
        "version": allocation.version,
        "status": allocation.status,
        "number": allocation.remote_number,
        "error_code": allocation.error_code,
        "error_detail": allocation.error_detail,
        "job": JobSerializer(allocation.current_job).data if allocation.current_job_id else None,
        "document": document,
        "created_at": allocation.created_at,
        "updated_at": allocation.updated_at,
    }


def _json_snapshot(validated_data):
    snapshot = {}
    for field, value in validated_data.items():
        if field == "panel":
            snapshot[field] = value.pk if value is not None else None
        elif field == "cover_page":
            snapshot[field] = {
                "issue": value.get("issue"),
                **({"version": value["version"]} if "version" in value else {}),
            }
        elif hasattr(value, "pk"):
            snapshot[field] = value.pk
        else:
            snapshot[field] = value
    return snapshot
