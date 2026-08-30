"""HTTP adapter for durable Teamcenter property updates."""

import json

from django.conf import settings
from django.core.files.base import ContentFile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser

from awcenter.api_errors import error_response
from jobs.api import job_creation_response
from jobs.services import create_job

from .serializers import SetPropertiesSerializer


@api_view(["POST"])
@permission_classes([IsAdminUser])
def create_property_update_job(request):
    """Queue a validated write instead of mutating Teamcenter in the web process."""

    if not settings.TEAMCENTER_ENABLED:
        return error_response(
            "Teamcenter is not enabled.",
            code="TEAMCENTER_NOT_CONFIGURED",
            response_status=503,
        )
    idempotency_key = str(request.headers.get("Idempotency-Key", "")).strip()
    if not idempotency_key:
        return error_response(
            "Idempotency-Key is required for external writes.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            response_status=400,
        )
    serializer = SetPropertiesSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    encoded = json.dumps(
        serializer.validated_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    job, created = create_job(
        request.user,
        "teamcenter.set_properties",
        "Update Teamcenter properties",
        {},
        ContentFile(encoded, name="teamcenter-property-update.json"),
        idempotency_key=idempotency_key,
        request_id=getattr(request, "request_id", ""),
        reconcile_on_lease_loss=True,
    )
    return job_creation_response(job, created)
