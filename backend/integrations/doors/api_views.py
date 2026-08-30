"""Durable, bridge-backed HTTP adapters for IBM Rational DOORS operations."""

import json

from django.core.files.base import ContentFile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from automations.catalog import JSON_OPERATION_POLICY
from awcenter.api_errors import error_response
from jobs.api import job_creation_response
from jobs.services import create_job

from .serializers import (
    ModuleSerializer,
    ModuleExportSerializer,
    ObjectCreateSerializer,
    ObjectDetailSerializer,
    ObjectListSerializer,
    ObjectUpdateSerializer,
    RequirementLinkSerializer,
)
from .services import integration_status


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    """Expose only the fail-closed Windows bridge capability state."""

    status = doors_bridge_status()
    return Response(status)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_module_check_job(request):
    """Queue one module accessibility check for a Windows bridge agent."""

    return enqueue_read_job(
        request,
        ModuleSerializer,
        "check_module",
        "Check DOORS module",
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_object_list_job(request):
    """Queue one bounded DOORS object listing operation."""

    return enqueue_read_job(
        request,
        ObjectListSerializer,
        "list_objects",
        "List DOORS objects",
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_module_export_job(request):
    """Queue one bounded module export for the compliance import linker."""

    return enqueue_read_job(
        request,
        ModuleExportSerializer,
        "export_module",
        "Export DOORS module for compliance import",
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_object_detail_job(request):
    """Queue one bounded DOORS object detail operation."""

    return enqueue_read_job(
        request,
        ObjectDetailSerializer,
        "get_object",
        "Read DOORS object",
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_discipline_check_job(request):
    """Queue one applicable-discipline calculation for a DOORS module."""

    return enqueue_read_job(
        request,
        ModuleSerializer,
        "check_applicable_disciplines",
        "Check DOORS disciplines",
    )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def create_object_update_job(request):
    """Queue one validated external write; the HTTP request never runs COM."""

    return enqueue_job(
        request,
        ObjectUpdateSerializer,
        "doors.update_object",
        "Update DOORS object",
    )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def create_object_create_job(request):
    """Queue one validated object creation for approval-aware job tracking."""

    return enqueue_job(
        request,
        ObjectCreateSerializer,
        "doors.create_object",
        "Create DOORS object",
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_requirement_link_job(request):
    """Queue a preview or administrator-only Requirement PoC link operation."""

    serializer = RequirementLinkSerializer(data=request.data)
    if set(request.data) - set(serializer.fields):
        raise ValidationError({"fields": "Unsupported request fields were provided."})
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    if values["activeness"] and not request.user.is_staff:
        return error_response(
            "Administrator access is required to create DOORS links.",
            code="DOORS_LINK_PERMISSION_REQUIRED",
            response_status=403,
        )
    return enqueue_validated_job(
        request,
        values,
        "doors.link_requirements",
        "Link DOORS PoC requirements" if values["activeness"] else "Preview DOORS PoC links",
        reconcile_on_lease_loss=values["activeness"],
    )


def enqueue_read_job(request, serializer_class, operation, title):
    """Serialize an allowlisted read operation into a private input artifact."""

    return enqueue_job(
        request,
        serializer_class,
        "doors.run_dxl",
        title,
        operation=operation,
    )


def enqueue_job(request, serializer_class, kind, title, operation=None):
    """Create or replay one owner-scoped Windows automation job."""

    serializer = serializer_class(data=request.data)
    if set(request.data) - set(serializer.fields):
        raise ValidationError({"fields": "Unsupported request fields were provided."})
    serializer.is_valid(raise_exception=True)
    payload = dict(serializer.validated_data)
    if operation:
        payload["operation"] = operation
    return enqueue_validated_job(request, payload, kind, title)


def enqueue_validated_job(
    request, payload, kind, title, *, reconcile_on_lease_loss=False
):
    """Persist an already validated JSON automation payload."""

    unavailable = bridge_unavailable_response()
    if unavailable:
        return unavailable
    idempotency_key = str(request.headers.get("Idempotency-Key", "")).strip()
    if not idempotency_key:
        return error_response(
            "Idempotency-Key is required for automation jobs.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            response_status=400,
        )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > JSON_OPERATION_POLICY.maximum_bytes:
        return error_response(
            "The DOORS operation payload exceeds the safety limit.",
            code="DOORS_OPERATION_PAYLOAD_LIMIT",
            response_status=400,
        )
    upload = ContentFile(encoded, name="doors-operation.json")
    job, created = create_job(
        request.user,
        kind,
        title,
        {},
        upload,
        idempotency_key=idempotency_key,
        request_id=getattr(request, "request_id", ""),
        reconcile_on_lease_loss=(
            reconcile_on_lease_loss
            or kind in {"doors.update_object", "doors.create_object"}
        ),
    )
    return job_creation_response(job, created)


def bridge_unavailable_response():
    """Fail closed instead of building an unclaimable external-write backlog."""

    if doors_bridge_status()["available"]:
        return None
    return error_response(
        "The Windows automation bridge is unavailable.",
        code="WINDOWS_BRIDGE_UNAVAILABLE",
        response_status=503,
    )


def doors_bridge_status():
    """Combine the integration feature flag with live bridge readiness."""

    status = integration_status()
    bridge = status["bridge"]
    return {
        "configured": status["configured"],
        "available": status["available"],
        "active_agents": bridge["active_agents"] if status["configured"] else 0,
        "transport": bridge["transport"],
    }
