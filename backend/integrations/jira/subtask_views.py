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
    SubtaskFieldInspectionSerializer,
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
    serializer = SubtaskFieldInspectionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        _connector, issue_key, _projects, metadata = inspect_subtask_target(
            request.user, serializer.validated_data["issue"],
            include_summary=serializer.validated_data["include_summary"],
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
        target = SubtaskTargetSerializer(data=request.data)
        target.is_valid(raise_exception=True)
        is_workbook = request.FILES.get("file") is not None
        _connector, issue_key, projects, metadata = inspect_subtask_target(
            request.user, target.validated_data["issue"], include_summary=is_workbook,
        )
        _serializer, items = parse_subtask_request(request, metadata=metadata)
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


def parse_subtask_request(request, *, metadata=None):
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
    raw_items = workbook_items(workbook, serializer.validated_data["mapping"], metadata=metadata)
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


def workbook_items(workbook, mapping, *, metadata=None):
    fields = {field["id"]: field for field in metadata or []}
    if metadata is not None:
        validate_workbook_mapping(mapping, fields)
    columns = workbook_columns(workbook)
    requested_columns = [item["column"] for item in mapping]
    missing = sorted(set(requested_columns) - set(columns))
    if missing:
        raise ValidationError({"mapping": f"Workbook columns are missing: {', '.join(missing)}"})
    try:
        import pandas as pd

        frame = pd.read_excel(
            workbook,
            dtype=object,
            usecols=[columns.index(column) for column in requested_columns],
            nrows=MAX_SUBTASKS_PER_BATCH + 1,
        )
        frame.columns = [str(column).strip() for column in frame.columns]
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
            field_by_column[column]: workbook_field_value(
                row[column], fields.get(field_by_column[column]), row_number=_index + 2, column=column,
            )
            for column in requested_columns
        }
        if all(value in (None, "") for value in values.values()):
            continue
        item = {
            "summary": values.pop("summary", ""),
            "description": values.pop("description", "") or "",
            "assignee": values.pop("assignee", "") or "",
            "due_date": workbook_due_date(values.pop("duedate", None)),
            "fields": {key: value for key, value in values.items() if value not in (None, "")},
        }
        items.append(item)
    return items



def validate_workbook_mapping(mapping, fields):
    """Never accept stale or protected mappings, including all-empty columns."""

    unknown = sorted({item["field"] for item in mapping} - fields.keys())
    if unknown:
        raise ValidationError({"mapping": "Reload JIRA fields; unavailable fields: " + ", ".join(unknown)})


def workbook_field_value(value, field, *, row_number, column):
    """Decode Excel's text cells by the live schema before bounded serialization.

    Lists use semicolon-separated values or JSON arrays; references may use bounded
    JSON objects. Ordinary text is never interpreted as JSON or split on delimiters.
    """

    if field is None:
        return workbook_value(value)
    schema = field.get("schema") or {}
    field_type = schema.get("type")
    try:
        if isinstance(value, (datetime, date)) and field_type == "datetime":
            # Excel dates have no timezone. Require an explicit offset in text cells.
            raise ValueError("Use ISO date-time text including a timezone, e.g. 2026-09-22T10:00:00+03:00.")
        value = workbook_value(value)
        if value in (None, ""):
            return value
        if field_type == "array":
            value = workbook_list_value(value)
            if schema.get("items") == "date":
                value = [workbook_due_date(item) for item in value]
            return value
        if field_type == "date":
            return workbook_due_date(value)
        if field_type not in {"string", "number", "integer", "float", "double", "boolean", "datetime"}:
            if isinstance(value, str) and value.startswith("{"):
                return json.loads(value)
        return value
    except (ValueError, ValidationError) as error:
        raise ValidationError({"file": f"Excel row {row_number}, column '{column}' ({field['name']}): invalid {field_type} value."}) from error


def workbook_list_value(value):
    if isinstance(value, str):
        if value.startswith("["):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("Use a JSON array.")
            return parsed
        return [item.strip() for item in value.split(";") if item.strip()]
    return [value]

def workbook_due_date(value):
    """Preserve the original Excel generator's day-first date formats."""

    if value in (None, ""):
        return None
    for date_format in (
        "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
        "%d %m %Y", "%d %B %Y", "%d %b %Y",
    ):
        try:
            return datetime.strptime(str(value), date_format).date().isoformat()
        except ValueError:
            continue
    # Invalid dates must be reported, not silently dropped from the user's subtask.
    raise ValidationError({"file": "A Due Date cell contains an unsupported date."})


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
