"""Preparation, validation, and upsert execution for CompDoc workbooks."""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import APIException

from .compdoc_import import build_mapping_preview, choose_header_row, read_mapped_excel
from .compdoc_import_plan import (
    build_import_plan,
    safe_row_error,
    summarize_import_plan,
    validation_error,
)
from .compdoc_import_values import get_mappable_import_fields


class CompDocImportLimitExceeded(APIException):
    """Reject workbooks whose row count exceeds the configured bound."""

    status_code = 400
    default_code = "COMPDOC_IMPORT_ROW_LIMIT"

    def __init__(self, row_count, row_limit):
        """Store safe counts for audit finalization and response guidance."""

        self.row_count = row_count
        detail = f"Workbook has {row_count} rows; the limit is {row_limit}."
        super().__init__(detail, self.default_code)


@dataclass(frozen=True)
class PreparedImport:
    """Hold mapped workbook data and its safe preview metadata."""

    dataframe: object
    header_result: object
    preview: dict


def prepare_import(uploaded_file, model):
    """Detect headers and return a null-normalized mapped dataframe."""

    import pandas as pd

    fields = get_mappable_import_fields(model)
    header_result = choose_header_row(uploaded_file, pd, fields)
    uploaded_file.seek(0)
    preview_frame = pd.read_excel(uploaded_file, header=header_result.header_row_index)
    preview = build_mapping_preview(preview_frame.columns, header_result)
    uploaded_file.seek(0)
    dataframe = read_mapped_excel(uploaded_file, pd, header_result)
    dataframe = dataframe.astype(object).where(pd.notnull(dataframe), None)
    ensure_row_limit(dataframe)
    return PreparedImport(dataframe, header_result, preview)


def ensure_row_limit(dataframe):
    """Reject excessive rows before validation or database work begins."""

    row_limit = max(int(settings.AWCENTER_MAX_COMPDOC_IMPORT_ROWS), 1)
    if len(dataframe) > row_limit:
        raise CompDocImportLimitExceeded(len(dataframe), row_limit)


def preview_import(prepared, model, serializer_class):
    """Return a persistence-free action plan and safe row failures."""

    return summarize_import_plan(build_import_plan(prepared, model, serializer_class))


def execute_import(prepared, model, serializer_class):
    """Upsert valid rows and return deterministic result counters."""

    plan = build_import_plan(prepared, model, serializer_class)
    result = summarize_import_plan(plan)
    created_count, updated_count, save_errors = save_rows(plan.rows, serializer_class)
    result["created_count"] = created_count
    result["updated_count"] = updated_count
    result["rejected_count"] += len(save_errors)
    result["errors"].extend(save_errors)
    return result


def save_rows(planned_rows, serializer_class):
    """Persist planned changes while skipping unchanged rows."""

    created_count = 0
    updated_count = 0
    errors = []
    for row in planned_rows:
        if row.action == "unchanged":
            continue
        _, row_error = save_row(row.instance, row.payload, serializer_class, row.row_number)
        if row_error:
            errors.append(row_error)
        elif row.action == "update":
            updated_count += 1
        else:
            created_count += 1
    return created_count, updated_count, errors


@transaction.atomic
def save_row(instance, payload, serializer_class, row_number):
    """Validate and persist one row inside an isolated transaction."""

    serializer = serializer_class(instance, data=payload)
    if not serializer.is_valid():
        return None, validation_error(row_number, payload, serializer.errors)
    try:
        return serializer.save(), None
    except Exception:
        return None, safe_row_error(row_number, payload, "ROW_SAVE_FAILED", "Row could not be saved.")
