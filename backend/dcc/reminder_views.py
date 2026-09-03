"""Authenticated Watcher reminder enqueue endpoint."""

from django.shortcuts import get_object_or_404
from jira import JIRAError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from integrations.jira.sessions import JiraSessionError, has_legacy_jira_credential

from .document_snapshot import DccSnapshotError
from .issue_draft_views import jira_session_error_response
from .access_policy import project_records_for_user
from .reminder_serializers import DccReminderCreateSerializer, DccReminderDeliverySerializer
from .reminder_service import enqueue_dcc_reminder


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_dcc_reminder(request, record_id):
    """Queue a reminder; the web process never receives SMTP credentials."""

    if has_legacy_jira_credential((request.data, request.query_params)):
        return error_response(
            "Connect JIRA through the integrations session endpoint.",
            "JIRA_SESSION_CANONICAL_REQUIRED",
            response_status=400,
        )
    get_object_or_404(project_records_for_user(request.user), pk=record_id)
    serializer = DccReminderCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        delivery, created = enqueue_dcc_reminder(
            request.user,
            record_id,
            serializer.validated_data,
            request.headers.get("Idempotency-Key", ""),
        )
    except JiraSessionError as error:
        return jira_session_error_response(error)
    except DccSnapshotError as error:
        return error_response(str(error), error.code, response_status=error.response_status)
    except (JIRAError, ValueError):
        return error_response(
            "JIRA could not prepare the reminder.",
            "DCC_REMINDER_JIRA_UNAVAILABLE",
            response_status=502,
        )
    response = Response(
        DccReminderDeliverySerializer(delivery).data,
        status=201 if created else 200,
    )
    if not created:
        response["Idempotency-Replayed"] = "true"
    return response
