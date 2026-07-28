from datetime import datetime

from django.db import migrations


PROJECTS = ("aesa", "blok30", "blok4050", "gokbey", "havasoj", "hys", "ozgur", "piku")
FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")


def backfill_events(apps, schema_editor):
    """Copy valid legacy workflow entries without altering their source JSON."""

    event_model = apps.get_model("common", "CompDocWorkflowEvent")
    for project in PROJECTS:
        document_model = apps.get_model(project, "CompDoc")
        pending = []
        for document in document_model.objects.only("id", "status_flow").iterator(chunk_size=500):
            previous = ""
            sequence = 0
            for item in document.status_flow or []:
                parsed = _event(item)
                if not parsed:
                    continue
                sequence += 1
                pending.append(event_model(
                    project_slug=project, document_id=document.pk, sequence=sequence,
                    previous_status=previous, status=parsed[0], effective_date=parsed[1],
                    reason=str(item.get("note") or "Legacy workflow migration")[:255],
                    source="migration",
                ))
                previous = parsed[0]
            if len(pending) >= 500:
                event_model.objects.bulk_create(pending, ignore_conflicts=True)
                pending = []
        event_model.objects.bulk_create(pending, ignore_conflicts=True)


def _event(item):
    if not isinstance(item, dict) or not str(item.get("status") or "").strip():
        return None
    for date_format in FORMATS:
        try:
            return str(item["status"]).strip(), datetime.strptime(
                str(item.get("date") or "").strip(), date_format
            ).date()
        except ValueError:
            continue
    return None


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("common", "0016_compdocreviewtask_compdocworkflowevent"),
        ("aesa", "0030_compdoc_archive_reason_compdoc_archived_at_and_more"),
        ("blok30", "0017_compdoc_archive_reason_compdoc_archived_at_and_more"),
        ("blok4050", "0006_compdoc_archive_reason_compdoc_archived_at_and_more"),
        ("gokbey", "0006_compdoc_archive_reason_compdoc_archived_at_and_more"),
        ("havasoj", "0020_compdoc_archive_reason_compdoc_archived_at_and_more"),
        ("hys", "0017_compdoc_archive_reason_compdoc_archived_at_and_more"),
        ("ozgur", "0023_compdoc_archive_reason_compdoc_archived_at_and_more"),
        ("piku", "0027_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ]
    operations = [migrations.RunPython(backfill_events, migrations.RunPython.noop)]
