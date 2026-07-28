"""Styled Excel export generation for project CompDoc models."""

import json

import pandas as pd
from django.conf import settings
from django.http import HttpResponse
from rest_framework.views import APIView

from awcenter.api_errors import error_response
from .compdoc_import_values import get_mappable_import_fields
from .compdoc_permissions import StrictDjangoModelPermissions
from .compdoc_excel_workbook import write_workbook
from .compdoc_workflow import WORKFLOW_STATUSES

LIST_COLUMNS = {"Signature Panel", "Requirements", "Status Flow"}
EXCLUDED_EXPORT_FIELDS = {
    "path",
    "tech_doc_no_2",
    "tech_doc_issue_2",
    "delivered_tech_doc_issue_2",
}
SECONDARY_FIELDS = (
    ("tech_doc_no", "tech_doc_no_2"),
    ("tech_doc_issue", "tech_doc_issue_2"),
    ("delivered_tech_doc_issue", "delivered_tech_doc_issue_2"),
)


def excel_creator_factory(model, serializer_class, view_permission_classes):
    """Return a project-specific CompDoc Excel export API view."""

    class ExcelCreator(APIView):
        """Download the current project CompDocs as a styled workbook."""

        queryset = model.objects.none()
        permission_classes = [*view_permission_classes, StrictDjangoModelPermissions]

        def get(self, request):
            """Build and return one in-memory OOXML workbook."""

            return build_excel_response(model, serializer_class)

    return ExcelCreator


def build_excel_response(model, serializer_class):
    """Serialize model rows and return a downloadable workbook response."""

    queryset = model.objects.all()
    row_count = queryset.count()
    row_limit = max(int(settings.AWCENTER_MAX_COMPDOC_EXPORT_ROWS), 1)
    if row_count > row_limit:
        return error_response(
            "The compliance register is too large for a synchronous export.",
            code="COMPDOC_EXPORT_ROW_LIMIT",
            response_status=413,
        )
    serialized_rows = serializer_class(queryset, many=True).data
    dataframe = prepare_export_dataframe(pd.DataFrame(serialized_rows), model)
    return _workbook_response(model, write_workbook(dataframe).getvalue())


def _workbook_response(model, content):
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    filename = f"{model._meta.app_label.upper()} Compliance Documents.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def prepare_export_dataframe(dataframe, model):
    """Return the model's complete, import-compatible public workbook schema."""

    for primary, secondary in SECONDARY_FIELDS:
        merge_secondary_column(dataframe, primary, secondary)
    add_status_columns(dataframe)
    dataframe = dataframe.reindex(columns=get_export_field_order(model))
    dataframe.columns = [str(column).replace("_", " ").title() for column in dataframe.columns]
    normalize_list_columns(dataframe)
    return dataframe


def get_export_field_order(model):
    """Return ordered model fields that the current importer accepts."""

    importable = get_mappable_import_fields(model)
    return [
        field.name
        for field in model._meta.fields
        if field.name in importable and field.name not in EXCLUDED_EXPORT_FIELDS
    ]


def merge_secondary_column(dataframe, primary, secondary):
    """Merge an optional secondary document value into its primary column."""

    if secondary not in dataframe.columns:
        return
    dataframe[primary] = dataframe.apply(
        lambda row: join_present_values(row.get(primary), row.get(secondary)), axis=1
    )
    dataframe.drop(columns=[secondary], inplace=True)


def join_present_values(primary, secondary):
    """Join non-null scalar values using the established newline format."""

    values = [value for value in (primary, secondary) if value is not None and not pd.isna(value)]
    return "\n".join(str(value) for value in values)


def add_status_columns(dataframe):
    """Derive target, delivery, and current status from status history."""

    if "status_flow" not in dataframe.columns:
        return
    dataframe["ubm_target_date"] = dataframe["status_flow"].apply(
        lambda flow: status_date(flow, "to_be_issued")
    )
    dataframe["ubm_delivery_date"] = dataframe["status_flow"].apply(
        lambda flow: status_date(flow, "authority_review")
    )
    dataframe["status"] = dataframe["status_flow"].apply(current_status)


def status_date(flow, status):
    """Return the first matching status date from a safe event list."""

    if not isinstance(flow, list):
        return None
    return next(
        (
            event.get("date")
            for event in flow
            if isinstance(event, dict) and event.get("status") == status
        ),
        None,
    )


def current_status(flow):
    """Return the last status identifier from a safe event list."""

    if not isinstance(flow, list) or not flow:
        return "unknown"
    events = [event for event in flow if isinstance(event, dict)]
    status = events[-1].get("status") if events else None
    return status if status in WORKFLOW_STATUSES else "unknown"


def normalize_list_columns(dataframe):
    """Render JSON list columns as newline-separated workbook cells."""

    for column in LIST_COLUMNS.intersection(dataframe.columns):
        formatter = format_status_flow if column == "Status Flow" else format_list_value
        dataframe[column] = dataframe[column].apply(formatter)


def format_list_value(value):
    """Return a stable workbook representation for a JSON-list value."""

    if isinstance(value, (list, tuple)):
        return "\n".join(map(str, value))
    return "" if value is None or pd.isna(value) else str(value)


def format_status_flow(value):
    """Render status events as one strict JSON object per line."""

    if not isinstance(value, (list, tuple)):
        return format_list_value(value)
    return "\n".join(
        json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)
        for event in value
    )
