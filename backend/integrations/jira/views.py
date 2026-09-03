"""Canonical owner-scoped JIRA session resource."""

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.api_errors import error_response

from .serializers import JiraSessionConnectSerializer
from .sessions import (
    JiraSessionError,
    clear_jira_session,
    connect_jira_session,
    get_jira_session,
    has_legacy_jira_credential,
)

logger = logging.getLogger(__name__)


class JiraSessionView(APIView):
    """Connect, inspect, or clear the current user's ephemeral JIRA session."""

    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        """Apply no-store to successful and rejected credential exchange responses."""

        finalized = super().finalize_response(request, response, *args, **kwargs)
        finalized["Cache-Control"] = "no-store"
        finalized["Pragma"] = "no-cache"
        return finalized

    def get(self, request):
        invalid = reject_query_credentials(request)
        if invalid:
            return invalid
        record = get_jira_session(request.user)
        if record is None:
            return no_store_response(disconnected_payload())
        return no_store_response(record.public_payload())

    def post(self, request):
        invalid = reject_query_credentials(request)
        if invalid:
            return invalid
        serializer = JiraSessionConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = connect_jira_session(
                request.user,
                serializer.validated_data["JSESSIONID"],
            )
        except JiraSessionError as error:
            return session_error_response(error)
        except Exception as error:
            logger.warning(
                "JIRA session connection failed failure_type=%s",
                error.__class__.__name__,
            )
            return error_response(
                "JIRA session validation is unavailable.",
                code="JIRA_SESSION_UNAVAILABLE",
                response_status=502,
            )
        return no_store_response(record.public_payload())

    def delete(self, request):
        invalid = reject_query_credentials(request)
        if invalid:
            return invalid
        clear_jira_session(request.user)
        return no_store_response(status=204)


def reject_query_credentials(request):
    if not has_legacy_jira_credential(request.query_params):
        return None
    return error_response(
        "Send JIRA credentials only in the canonical session POST body.",
        code="JIRA_SESSION_QUERY_FORBIDDEN",
        response_status=400,
    )


def session_error_response(error):
    return error_response(
        error.detail,
        code=error.code,
        response_status=error.response_status,
    )


def disconnected_payload():
    return {"state": "disconnected", "user": None, "expires_at": None}


def no_store_response(data=None, *, status=200):
    """Prevent browsers and intermediaries from caching session lifecycle responses."""

    response = Response(data, status=status)
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response
