"""Calendar-week and explicitly chosen compatible report comparisons."""

from datetime import date, timedelta
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from management_reports.access import authorized_projects
from management_reports.models import ReportSnapshot
from management_reports.services import METRIC_KEYS, report_list_item, scope_key


def compare_report(user, report, baseline_id=None):
    """Compare net stock values against an accessible compatible capture."""
    captured_at = parse_datetime(report["captured_at"])
    week_start = date.fromisoformat(report["week_start"])
    compatible = ReportSnapshot.objects.filter(
        owner=user,
        scope_key=scope_key(report["project_slugs"]),
        schema_version=report["schema_version"],
        captured_at__lt=captured_at,
    )
    if baseline_id is not None:
        baseline = _explicit_baseline(user, report, captured_at, baseline_id)
    else:
        baseline = compatible.filter(
            week_start=week_start - timedelta(days=7)
        ).first()
    if baseline is None:
        return {
            "available": False, "baseline": None,
            "elapsed_days": None, "deltas": None,
        }
    authorized_projects(user, baseline.project_slugs)
    return {
        "available": True,
        "baseline": report_list_item(baseline),
        "elapsed_days": round(
            (captured_at - baseline.captured_at).total_seconds() / 86400, 2
        ),
        "deltas": {
            key: round(report["totals"][key] - baseline.payload["totals"][key], 1)
            for key in METRIC_KEYS
        },
    }


def _explicit_baseline(user, report, captured_at, baseline_id):
    try:
        identifier = UUID(str(baseline_id))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"baseline": "Expected a report UUID."})
    baseline = get_object_or_404(
        ReportSnapshot.objects.filter(owner=user), pk=identifier
    )
    authorized_projects(user, baseline.project_slugs)
    if baseline.project_slugs != report["project_slugs"]:
        raise ValidationError({"baseline": "Baseline scope must match the report."})
    if baseline.schema_version != report["schema_version"]:
        raise ValidationError({"baseline": "Baseline schema must match the report."})
    if baseline.captured_at >= captured_at:
        raise ValidationError({"baseline": "Baseline must be older than the report."})
    return baseline
