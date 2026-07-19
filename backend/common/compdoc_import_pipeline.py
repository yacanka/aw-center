"""Preparation, validation, and upsert execution for CompDoc workbooks."""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import APIException

from .compdoc_import import build_mapping_preview, choose_header_row, read_mapped_excel
from .compdoc_import_values import get_mappable_import_fields, normalize_import_row

MAX_ERROR_TEXT = 500


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
    """Return safe row validation errors without changing persistence."""

    normalized_rows, errors = normalize_rows(prepared, model)
    existing = load_existing_instances(model, normalized_rows)
    for row_number, payload in normalized_rows:
        instance = existing.get(payload.get("cover_page_no"))
        serializer = serializer_class(instance, data=payload)
        if not serializer.is_valid():
            errors.append(validation_error(row_number, payload, serializer.errors))
    return errors


def execute_import(prepared, model, serializer_class):
    """Upsert valid rows and return deterministic result counters."""

    normalized_rows, errors = normalize_rows(prepared, model)
    existing = load_existing_instances(model, normalized_rows)
    created_count, updated_count = save_rows(normalized_rows, existing, serializer_class, errors)
    return {
        "created_count": created_count,
        "updated_count": updated_count,
        "rejected_count": len(errors),
        "errors": errors,
    }


def normalize_rows(prepared, model):
    """Normalize all rows while isolating deterministic row errors."""

    normalized_rows = []
    errors = []
    for row_index, row in prepared.dataframe.iterrows():
        row_number = workbook_row_number(row_index, prepared.header_result)
        try:
            normalized_rows.append((row_number, normalize_import_row(row.to_dict(), model)))
        except (TypeError, ValueError, SyntaxError) as error:
            errors.append(transform_error(row_number, row.to_dict(), error))
    return normalized_rows, errors


def load_existing_instances(model, normalized_rows):
    """Load all existing upsert targets in one bounded query."""

    keys = [payload.get("cover_page_no") for _, payload in normalized_rows]
    keys = [key for key in keys if key]
    return model.objects.in_bulk(keys, field_name="cover_page_no")


def save_rows(normalized_rows, existing, serializer_class, errors):
    """Save normalized rows and update the in-memory upsert index."""

    created_count = 0
    updated_count = 0
    for row_number, payload in normalized_rows:
        instance = existing.get(payload.get("cover_page_no"))
        saved, row_error = save_row(instance, payload, serializer_class, row_number)
        if row_error:
            errors.append(row_error)
        elif instance:
            updated_count += 1
        else:
            created_count += 1
            existing[saved.cover_page_no] = saved
    return created_count, updated_count


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


def validation_error(row_number, payload, errors):
    """Return a bounded serializer validation summary."""

    fields = sanitize_field_errors(errors)
    result = safe_row_error(row_number, payload, "ROW_VALIDATION_FAILED", "Validation failed.")
    result["fields"] = fields
    result["error_text"] = format_field_errors(fields)
    return result


def transform_error(row_number, raw_values, error):
    """Return a bounded value-transformation summary."""

    detail = str(error)[:MAX_ERROR_TEXT] or "Row values could not be normalized."
    return safe_row_error(row_number, raw_values, "ROW_TRANSFORM_FAILED", detail)


def safe_row_error(row_number, values, code, detail):
    """Return audit-safe row identity and recovery detail."""

    name = str(values.get("name") or f"Row {row_number}")[:256]
    return {"row": row_number, "name": name, "code": code, "detail": detail[:MAX_ERROR_TEXT]}


def sanitize_field_errors(errors):
    """Return bounded serializer field messages without internal values."""

    return {
        str(field)[:64]: [str(message)[:MAX_ERROR_TEXT] for message in messages][:10]
        for field, messages in dict(errors).items()
    }


def format_field_errors(errors):
    """Return a compact validation string for the existing upload UI."""

    return "; ".join(f"{field}: {', '.join(messages)}" for field, messages in errors.items())


def workbook_row_number(row_index, header_result):
    """Return the one-based source workbook row number."""

    return int(row_index) + header_result.header_row_index + 2
