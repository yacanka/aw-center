"""Canonical Watcher routes; no browser-supplied integration credentials."""

from django.shortcuts import get_object_or_404
from jira import JIRAError
from requests.exceptions import RequestException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from integrations.jira.sessions import JiraSessionError
from .access_policy import project_records_for_user
from .document_snapshot import DccSnapshotError
from .issue_draft_views import jira_session_error_response
from .serializers import DccRecordSerializer
from .subtask_serializers import SubtaskTargetSerializer
from .subtask_views import reject_legacy_session
from .watcher_service import import_watcher_record, live_watcher_status


def watcher_response(operation):
    try:
        return operation()
    except JiraSessionError as error:
        return jira_session_error_response(error)
    except DccSnapshotError as error:
        return error_response(str(error), error.code, response_status=error.response_status)
    except (JIRAError, RequestException):
        return error_response("JIRA could not load the task. Check the connection and retry.",
                              "DCC_WATCHER_JIRA_UNAVAILABLE", response_status=502)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_watcher_issue(request):
    legacy_error = reject_legacy_session(request)
    if legacy_error:
        return legacy_error
    serializer = SubtaskTargetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return watcher_response(lambda: Response(DccRecordSerializer(import_watcher_record(
        request.user, serializer.validated_data["issue"])).data, status=201))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def watcher_status(request, record_id):
    legacy_error = reject_legacy_session(request)
    if legacy_error:
        return legacy_error
    record = get_object_or_404(project_records_for_user(request.user), pk=record_id)
    return watcher_response(lambda: Response(live_watcher_status(request.user, record)))
