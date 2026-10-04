"""Date parsing shared by compliance imports and workflow transitions."""

from datetime import date, datetime


DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")


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
