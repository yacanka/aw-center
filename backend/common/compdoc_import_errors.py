"""Safe row-level error helpers for compliance-document imports."""

MAX_ERROR_TEXT = 500


def duplicate_error(row_number, payload):
    """Return an ambiguity error for a repeated business key."""

    return safe_row_error(
        row_number,
        payload,
        "ROW_DUPLICATE_KEY",
        "Cover page and technical document identity appear more than once in the workbook.",
    )


def archived_error(row_number, payload):
    """Require an explicit restore before an archived identity can be imported."""

    return safe_row_error(
        row_number,
        payload,
        "ROW_ARCHIVED_CONFLICT",
        "This document is archived. Restore it before importing an update.",
    )


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
