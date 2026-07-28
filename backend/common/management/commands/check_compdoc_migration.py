"""Report anonymous CompDoc migration readiness counts."""

from django.apps import apps
from django.core.management.base import BaseCommand

from common.compdoc_workflow import parse_workflow_date
from projects.registry import PROJECT_DEFINITIONS


class Command(BaseCommand):
    """Check data quality without emitting document content or personal data."""

    help = "Report anonymous CompDoc lifecycle migration readiness counts."

    def handle(self, *args, **options):
        for slug in PROJECT_DEFINITIONS:
            model = apps.get_model(slug, "CompDoc")
            counts = _project_counts(model)
            summary = " ".join(f"{key}={value}" for key, value in counts.items())
            self.stdout.write(f"{slug}: {summary}")


def _project_counts(model):
    counts = {
        "documents": model.objects.count(),
        "blank_cover_page": 0,
        "long_cover_page": 0,
        "invalid_panel_ata": 0,
        "invalid_workflow": 0,
        "valid_events": 0,
    }
    panels = set(
        model._meta.apps.get_model(model._meta.app_label, "Panel").objects.values_list(
            "name", "ata"
        )
    )
    fields = ("cover_page_no", "panel", "ata", "status_flow")
    for document in model.objects.values(*fields).iterator(chunk_size=500):
        _inspect_document(document, panels, counts)
    return counts


def _inspect_document(document, panels, counts):
    cover_page = str(document["cover_page_no"] or "").strip()
    counts["blank_cover_page"] += not cover_page
    counts["long_cover_page"] += len(cover_page) > 32
    if document["panel"] and document["ata"]:
        counts["invalid_panel_ata"] += (document["panel"], document["ata"]) not in panels
    flow = document["status_flow"]
    if not isinstance(flow, list):
        counts["invalid_workflow"] += 1
        return
    for event in flow:
        if _valid_event(event):
            counts["valid_events"] += 1
        else:
            counts["invalid_workflow"] += 1


def _valid_event(event):
    if not isinstance(event, dict) or not str(event.get("status") or "").strip():
        return False
    return parse_workflow_date(event.get("date")) is not None
