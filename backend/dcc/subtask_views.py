"""Authenticated HTTP surface for credential-free JIRA subtask workflows."""

import json
from datetime import date, datetime

from jira import JIRAError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from awcenter.file_security import EXCEL_POLICY, validate_request_upload
from integrations.jira.sessions import JiraSessionError, has_legacy_jira_credential
from jobs.api import job_creation_response

from .document_snapshot import DccSnapshotError
from .issue_draft_views import jira_session_error_response
from .subtask_contracts import inspect_subtask_target, validate_item_field_contract
from .subtask_jobs import enqueue_subtask_batch, enqueue_subtask_resume
from .subtask_serializers import (
    MAX_SUBTASKS_PER_BATCH,
    SubtaskBatchSerializer,
    SubtaskTargetSerializer,
    SubtaskWorkbookSerializer,
)

MAX_WORKBOOK_COLUMNS = 100


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def inspect_subtask_fields(request):
    """Return the live, sanitized subtask create contract for one parent issue."""

    legacy_error = reject_legacy_session(request)
    if legacy_error:
        return legacy_error
    serializer = SubtaskTargetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        _connector, issue_key, _projects, metadata = inspect_subtask_target(
            request.user, serializer.validated_data["issue"]
        )
    except JiraSessionError as error:
        return jira_session_error_response(error)
    except DccSnapshotError as error:
        return error_response(str(error), error.code, response_status=error.response_status)
    except JIRAError:
        return error_response(
            "JIRA could not inspect subtask fields.",
            "JIRA_SUBTASK_FIELDS_UNAVAILABLE",
            response_status=502,
        )
    return Response({"issue": issue_key, "fields": metadata})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def inspect_subtask_workbook(request):
    """Return bounded first-sheet column names without retaining the workbook."""

    legacy_error = reject_legacy_session(request)
    if legacy_error:
        return legacy_error
    workbook = validate_request_upload(request, "file", EXCEL_POLICY)
    columns = workbook_columns(workbook)
    return Response({"columns": columns})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_subtask_job(request):
    """Validate a manual or workbook batch and enqueue one external-write job."""

    legacy_error = reject_legacy_session(request)
    if legacy_error:
        return legacy_error
    try:
        serializer, items = parse_subtask_request(request)
        _connector, issue_key, projects, metadata = inspect_subtask_target(
            request.user, serializer.validated_data["issue"]
        )
        validate_item_field_contract(items, metadata)
        job, created = enqueue_subtask_batch(
            request.user,
            issue_key,
            projects,
            items,
            request.headers.get("Idempotency-Key", ""),
            getattr(request, "request_id", ""),
        )
    except JiraSessionError as error:
        return jira_session_error_response(error)
    except DccSnapshotError as error:
        return error_response(str(error), error.code, response_status=error.response_status)
    except JIRAError:
        return error_response(
            "JIRA could not validate the subtask request.",
            "JIRA_SUBTASK_PREFLIGHT_UNAVAILABLE",
            response_status=502,
        )
    return job_creation_response(job, created)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resume_subtask_job(request, job_id):
    """Explicitly reconcile markers and continue an interrupted subtask batch."""

    legacy_error = reject_legacy_session(request)
    if legacy_error:
        return legacy_error
    try:
        job, created = enqueue_subtask_resume(
            request.user,
            job_id,
            request.headers.get("Idempotency-Key", ""),
            getattr(request, "request_id", ""),
        )
    except JiraSessionError as error:
        return jira_session_error_response(error)
    return job_creation_response(job, created)


def parse_subtask_request(request):
    workbook = request.FILES.get("file")
    if workbook is None:
        serializer = SubtaskBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer, serializer.validated_data["items"]

    validate_request_upload(request, "file", EXCEL_POLICY)
    raw_mapping = request.data.get("mapping")
    try:
        mapping = json.loads(raw_mapping) if isinstance(raw_mapping, str) else raw_mapping
    except json.JSONDecodeError as error:
        raise ValidationError({"mapping": "Enter a valid workbook mapping."}) from error
    serializer = SubtaskWorkbookSerializer(
        data={"issue": request.data.get("issue"), "mapping": mapping}
    )
    serializer.is_valid(raise_exception=True)
    raw_items = workbook_items(workbook, serializer.validated_data["mapping"])
    batch = SubtaskBatchSerializer(
        data={"issue": serializer.validated_data["issue"], "items": raw_items}
    )
    batch.is_valid(raise_exception=True)
    return batch, batch.validated_data["items"]


def workbook_columns(workbook):
    try:
        import pandas as pd

        frame = pd.read_excel(workbook, nrows=0)
    except Exception as error:
        raise ValidationError({"file": "The workbook first sheet could not be read."}) from error
    columns = [str(column).strip() for column in frame.columns]
    if not columns or len(columns) > MAX_WORKBOOK_COLUMNS:
        raise ValidationError({"file": "Use a workbook containing 1-100 columns."})
    if any(not column or len(column) > 200 for column in columns):
        raise ValidationError({"file": "Workbook column names must be 1-200 characters."})
    if len(set(columns)) != len(columns):
        raise ValidationError({"file": "Workbook column names must be unique."})
    workbook.seek(0)
    return columns


def workbook_items(workbook, mapping):
    columns = workbook_columns(workbook)
    requested_columns = [item["column"] for item in mapping]
    missing = sorted(set(requested_columns) - set(columns))
    if missing:
        raise ValidationError({"mapping": f"Workbook columns are missing: {', '.join(missing)}"})
    try:
        import pandas as pd

        frame = pd.read_excel(workbook, dtype=object, usecols=requested_columns)
    except Exception as error:
        raise ValidationError({"file": "The workbook first sheet could not be read."}) from error
    if len(frame.index) > MAX_SUBTASKS_PER_BATCH:
        raise ValidationError(
            {"file": f"Use at most {MAX_SUBTASKS_PER_BATCH} workbook rows."}
        )
    field_by_column = {item["column"]: item["field"] for item in mapping}
    items = []
    for _index, row in frame.iterrows():
        values = {
            field_by_column[column]: workbook_value(row[column])
            for column in requested_columns
        }
        if all(value in (None, "") for value in values.values()):
            continue
        item = {
            "summary": values.pop("summary", ""),
            "description": values.pop("description", ""),
            "assignee": values.pop("assignee", ""),
            "due_date": values.pop("duedate", None),
            "fields": {key: value for key, value in values.items() if value not in (None, "")},
        }
        items.append(item)
    return items


def workbook_value(value):
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return value
    return str(value).strip()


def reject_legacy_session(request):
    if not has_legacy_jira_credential((request.data, request.query_params)):
        return None
    return error_response(
        "Connect JIRA through the integrations session endpoint.",
        "JIRA_SESSION_CANONICAL_REQUIRED",
        response_status=400,
    )
