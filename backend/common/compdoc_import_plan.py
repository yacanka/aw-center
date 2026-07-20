"""Read-only planning for deterministic compliance-document imports."""

from collections import Counter
from dataclasses import dataclass

from .compdoc_import_values import normalize_import_row

MAX_ERROR_TEXT = 500


@dataclass(frozen=True, slots=True)
class PlannedImportRow:
    """Describe one validated workbook row and its intended database action."""

    row_number: int
    payload: dict
    instance: object
    action: str


@dataclass(frozen=True, slots=True)
class CompDocImportPlan:
    """Hold validated row actions and safe row-level failures."""

    rows: tuple[PlannedImportRow, ...]
    errors: tuple[dict, ...]


def build_import_plan(prepared, model, serializer_class):
    """Build a persistence-free create/update/unchanged plan."""

    normalized_rows, errors = normalize_rows(prepared, model)
    duplicates = duplicate_keys(normalized_rows)
    existing = load_existing_instances(model, normalized_rows)
    planned_rows = []
    for row_number, payload in normalized_rows:
        planned, error = plan_row(row_number, payload, duplicates, existing, serializer_class)
        if error:
            errors.append(error)
        elif planned:
            planned_rows.append(planned)
    return CompDocImportPlan(tuple(planned_rows), tuple(errors))


def summarize_import_plan(plan):
    """Return action counters and safe failures for API responses."""

    counts = Counter(row.action for row in plan.rows)
    return {
        "created_count": counts["create"],
        "updated_count": counts["update"],
        "unchanged_count": counts["unchanged"],
        "rejected_count": len(plan.errors),
        "errors": list(plan.errors),
    }


def normalize_rows(prepared, model):
    """Normalize all rows while isolating deterministic transformation errors."""

    normalized_rows, errors = [], []
    for row_index, row in prepared.dataframe.iterrows():
        row_number = workbook_row_number(row_index, prepared.header_result)
        try:
            normalized_rows.append((row_number, normalize_import_row(row.to_dict(), model)))
        except (TypeError, ValueError, SyntaxError) as error:
            errors.append(transform_error(row_number, row.to_dict(), error))
    return normalized_rows, errors


def duplicate_keys(normalized_rows):
    """Return business keys that occur more than once in the workbook."""

    counts = Counter(payload.get("cover_page_no") for _, payload in normalized_rows)
    return {key for key, count in counts.items() if key and count > 1}


def load_existing_instances(model, normalized_rows):
    """Load all existing upsert targets in one bounded query."""

    keys = {payload.get("cover_page_no") for _, payload in normalized_rows}
    return model.objects.in_bulk([key for key in keys if key], field_name="cover_page_no")


def plan_row(row_number, payload, duplicates, existing, serializer_class):
    """Validate one row and resolve its intended persistence action."""

    if payload.get("cover_page_no") in duplicates:
        return None, duplicate_error(row_number, payload)
    instance = existing.get(payload.get("cover_page_no"))
    serializer = serializer_class(instance, data=payload)
    if not serializer.is_valid():
        return None, validation_error(row_number, payload, serializer.errors)
    action = resolve_action(instance, serializer.validated_data)
    return PlannedImportRow(row_number, payload, instance, action), None


def resolve_action(instance, validated_data):
    """Resolve create, update, or unchanged from validated model values."""

    if instance is None:
        return "create"
    changed = any(getattr(instance, field) != value for field, value in validated_data.items())
    return "update" if changed else "unchanged"


def duplicate_error(row_number, payload):
    """Return an ambiguity error for a repeated business key."""

    return safe_row_error(
        row_number,
        payload,
        "ROW_DUPLICATE_KEY",
        "Cover page number appears more than once in the workbook.",
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
