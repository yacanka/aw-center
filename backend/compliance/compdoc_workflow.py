"""Workflow projection helpers for compliance documents."""

from dataclasses import dataclass
from datetime import date, datetime


WORKFLOW_STATUS_CHOICES = (
    ("to_be_issued", "To be Issued"),
    ("airworthiness_review", "Airworthiness Review"),
    ("to_be_re-submitted", "To be Re-Submitted"),
    ("to_be_updated", "To be Updated"),
    ("authority_review", "Authority Review"),
    ("authority_approved", "Authority Approved"),
    ("unknown", "Unknown"),
)
WORKFLOW_STATUSES = {value for value, _label in WORKFLOW_STATUS_CHOICES}
DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")


@dataclass(frozen=True)
class WorkflowProjection:
    """Queryable fields derived from the workflow event list."""

    status: str
    target_date: date | None
    delivery_date: date | None


def extract_workflow_projection(value) -> WorkflowProjection:
    """Return safe current-status and milestone projections from JSON data."""

    entries = [item for item in value if _valid_entry(item)] if isinstance(value, list) else []
    candidate = entries[-1]["status"].strip() if entries else "unknown"
    status = candidate if candidate in WORKFLOW_STATUSES else "unknown"
    target_date = parse_workflow_date(entries[0].get("date")) if entries else None
    delivery_date = parse_workflow_date(entries[1].get("date")) if len(entries) > 1 else None
    return WorkflowProjection(status, target_date, delivery_date)


def parse_workflow_date(value) -> date | None:
    """Parse supported workflow date representations without raising."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


def _valid_entry(value):
    return isinstance(value, dict) and isinstance(value.get("status"), str) and value["status"].strip()
