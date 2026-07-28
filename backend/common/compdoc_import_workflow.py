"""Lossless workflow parsing and reconciliation for CompDoc workbooks."""

import ast
import json
import math
from datetime import date, datetime

from dateutil import parser

from common.compdoc_workflow import WORKFLOW_STATUSES

MAX_STATUS_EVENTS = 50


def normalize_status(value):
    """Return a canonical, supported workflow status identifier."""

    if is_missing_workbook_value(value):
        raise ValueError("A status value is required.")
    status = str(value).strip().lower().replace(".", "").replace(" ", "_")
    if status not in WORKFLOW_STATUSES:
        raise ValueError(f"Unsupported workflow status: {status}")
    return status


def build_status_flow(raw_values, status):
    """Preserve exported history while applying edited status and milestone cells."""

    explicit_flow = parse_status_flow(raw_values.get("status_flow"))
    if explicit_flow:
        return reconcile_status_flow(explicit_flow, raw_values, status)
    target_value = raw_values.get("ubm_target_date")
    delivery = raw_values.get("ubm_delivery_date")
    if status == "unknown" and all(
        is_missing_workbook_value(value) for value in (target_value, delivery)
    ):
        return []
    target = format_date(target_value)
    flow = [{"status": "to_be_issued", "date": target}]
    if not is_missing_workbook_value(delivery):
        flow.append({"status": "authority_review", "date": format_date(delivery)})
    if status not in {"to_be_issued", "authority_review"}:
        flow.append({"status": status, "date": format_date(None)})
    return flow


def reconcile_status_flow(events, raw_values, status):
    """Apply operator-edited display columns without discarding prior events."""

    reconciled = [dict(event) for event in events]
    _set_milestone(reconciled, "to_be_issued", raw_values.get("ubm_target_date"), 0)
    _set_milestone(reconciled, "authority_review", raw_values.get("ubm_delivery_date"), 1)
    if reconciled[-1]["status"] != status:
        reconciled.append({"status": status, "date": format_date(None)})
    return reconciled


def parse_status_flow(value):
    """Parse one JSON event per line with a safe legacy-literal fallback."""

    if is_missing_workbook_value(value):
        return []
    if isinstance(value, list):
        return validate_status_events(value)
    events = [parse_status_event(line) for line in str(value).splitlines() if line.strip()]
    return validate_status_events(events)


def parse_status_event(value):
    """Parse strict JSON or a non-executable Python literal."""

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return ast.literal_eval(value)


def validate_status_events(events):
    """Return canonical event copies or reject malformed workbook history."""

    if len(events) > MAX_STATUS_EVENTS:
        raise ValueError("Status history exceeds 50 events.")
    normalized = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Status history must contain objects.")
        item = dict(event)
        item["status"] = normalize_status(item.get("status"))
        if not is_missing_workbook_value(item.get("date")):
            item["date"] = format_date(item["date"])
        normalized.append(item)
    return normalized


def format_date(value):
    """Return the established European workflow date representation."""

    if is_missing_workbook_value(value):
        return date.today().strftime("%d.%m.%Y")
    if isinstance(value, (datetime, date)):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip()
    for date_format in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return parser.parse(text, dayfirst=True).strftime("%d.%m.%Y")


def _set_milestone(events, status, value, insertion_index):
    if is_missing_workbook_value(value):
        return
    formatted = format_date(value)
    for event in events:
        if event["status"] == status:
            event["date"] = formatted
            return
    events.insert(min(insertion_index, len(events)), {"status": status, "date": formatted})


def is_missing_workbook_value(value):
    """Return whether a pandas/openpyxl scalar represents an empty cell."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    return isinstance(value, float) and math.isnan(value)
