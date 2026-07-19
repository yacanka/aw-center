"""Pure value normalization for CompDoc spreadsheet rows."""

import ast
import json
from datetime import date, datetime

from dateutil import parser

VIRTUAL_IMPORT_FIELDS = {"status", "ubm_target_date", "ubm_delivery_date"}
LIST_FIELDS = {"requirements", "signature_panel"}
MAX_STATUS_EVENTS = 50


def get_actual_import_fields(model):
    """Return editable, non-primary model fields accepted from imports."""

    return {
        field.name
        for field in model._meta.fields
        if field.editable and not field.primary_key and field.name != "created_time"
    }


def get_mappable_import_fields(model):
    """Return model and virtual workbook fields used during header matching."""

    return get_actual_import_fields(model) | VIRTUAL_IMPORT_FIELDS


def normalize_import_row(raw_values, model):
    """Convert one mapped workbook row into serializer-safe model values."""

    actual_fields = get_actual_import_fields(model)
    values = {key: value for key, value in raw_values.items() if key in actual_fields}
    status = normalize_status(raw_values.get("status"))
    normalize_simple_fields(values)
    normalize_multivalue_fields(values, actual_fields)
    for field in LIST_FIELDS:
        if field in actual_fields:
            values[field] = normalize_list(values.get(field))
    values["status_flow"] = build_status_flow(raw_values, status)
    return values


def normalize_status(value):
    """Return the canonical status identifier required for status history."""

    if value is None or not str(value).strip():
        raise ValueError("A status value is required.")
    return str(value).strip().lower().replace(".", "").replace(" ", "_")


def normalize_simple_fields(values):
    """Normalize common scalar workbook values in place."""

    if values.get("cover_page_no") is None or not str(values["cover_page_no"]).strip():
        raise ValueError("Cover page number is required.")
    if values.get("ata") is not None:
        values["ata"] = str(values["ata"]).strip()
    if values.get("cover_page_issue") is not None:
        values["cover_page_issue"] = normalize_issue(values["cover_page_issue"])
    if values.get("cover_page_no") is not None:
        values["cover_page_no"] = str(values["cover_page_no"]).strip()


def normalize_multivalue_fields(values, actual_fields):
    """Split primary and optional secondary document values in place."""

    split_value(values, actual_fields, "tech_doc_no", "tech_doc_no_2", str)
    split_value(values, actual_fields, "tech_doc_issue", "tech_doc_issue_2", normalize_issue)
    split_value(
        values,
        actual_fields,
        "delivered_tech_doc_issue",
        "delivered_tech_doc_issue_2",
        normalize_issue,
    )


def split_value(values, actual_fields, primary, secondary, converter):
    """Split newline-separated values into supported model fields."""

    raw_value = values.get(primary)
    if raw_value is None:
        return
    parts = [converter(item.strip()) for item in str(raw_value).splitlines() if item.strip()]
    values[primary] = parts[0] if parts else None
    if secondary in actual_fields:
        values[secondary] = parts[1] if len(parts) > 1 else None


def normalize_issue(value):
    """Return a stable integer-like issue string."""

    return str(int(float(str(value).strip())))


def normalize_list(value):
    """Return a JSON-list value from a list or newline-separated cell."""

    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value).splitlines() if item.strip()]


def build_status_flow(raw_values, status):
    """Return explicit status history or synthesize it from import dates."""

    explicit_flow = parse_status_flow(raw_values.get("status_flow"))
    if explicit_flow:
        return explicit_flow
    flow = [{"status": "to_be_issued", "date": format_date(raw_values.get("ubm_target_date"))}]
    delivery_date = raw_values.get("ubm_delivery_date")
    if delivery_date is not None:
        flow.append({"status": "authority_review", "date": format_date(delivery_date)})
    if status not in {"to_be_issued", "authority_review"}:
        flow.append({"status": status, "date": format_date(None)})
    return flow


def parse_status_flow(value):
    """Parse bounded JSON or Python-literal status events without execution."""

    if value is None or value == "":
        return []
    if isinstance(value, list):
        return validate_status_events(value)
    events = [parse_status_event(line) for line in str(value).splitlines() if line.strip()]
    return validate_status_events(events)


def parse_status_event(value):
    """Parse one status event from strict JSON or a safe literal fallback."""

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return ast.literal_eval(value)


def validate_status_events(events):
    """Reject malformed or excessive status history payloads."""

    if len(events) > MAX_STATUS_EVENTS:
        raise ValueError("Status history exceeds 50 events.")
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Status history must contain objects.")
    return events


def format_date(value):
    """Return the established European status-history date format."""

    if value is None:
        return date.today().strftime("%d.%m.%Y")
    if isinstance(value, (datetime, date)):
        return value.strftime("%d.%m.%Y")
    return parser.parse(str(value)).strftime("%d.%m.%Y")
