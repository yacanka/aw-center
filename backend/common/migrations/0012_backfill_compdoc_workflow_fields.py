from datetime import datetime

from django.db import migrations


PROJECTS = ("aesa", "blok30", "blok4050", "gokbey", "havasoj", "hys", "ozgur", "piku")
STATUSES = {
    "to_be_issued",
    "airworthiness_review",
    "to_be_re-submitted",
    "to_be_updated",
    "authority_review",
    "authority_approved",
}
DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")
FIELDS = ("status", "ubm_target_date", "ubm_delivery_date")


def backfill_workflow_fields(apps, schema_editor):
    """Populate query projections for current and historical compliance documents."""

    for app_label in PROJECTS:
        _backfill_model(apps.get_model(app_label, "CompDoc"))
        _backfill_model(apps.get_model(app_label, "HistoricalCompDoc"))


def _backfill_model(model):
    batch = []
    for document in model.objects.only("status_flow").iterator(chunk_size=500):
        status, target_date, delivery_date = _projection(document.status_flow)
        document.status = status
        document.ubm_target_date = target_date
        document.ubm_delivery_date = delivery_date
        batch.append(document)
        if len(batch) == 500:
            model.objects.bulk_update(batch, FIELDS)
            batch = []
    if batch:
        model.objects.bulk_update(batch, FIELDS)


def _projection(value):
    entries = [entry for entry in value if _valid_entry(entry)] if isinstance(value, list) else []
    candidate = entries[-1]["status"].strip() if entries else "unknown"
    status = candidate if candidate in STATUSES else "unknown"
    target_date = _parse_date(entries[0].get("date")) if entries else None
    delivery_date = _parse_date(entries[1].get("date")) if len(entries) > 1 else None
    return status, target_date, delivery_date


def _valid_entry(value):
    return isinstance(value, dict) and isinstance(value.get("status"), str) and value["status"].strip()


def _parse_date(value):
    if not isinstance(value, str):
        return None
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0011_coverpage_historicalcoverpage"),
        ("aesa", "0029_compdoc_status_compdoc_ubm_delivery_date_and_more"),
        ("blok30", "0016_compdoc_status_compdoc_ubm_delivery_date_and_more"),
        ("blok4050", "0005_compdoc_status_compdoc_ubm_delivery_date_and_more"),
        ("gokbey", "0005_compdoc_status_compdoc_ubm_delivery_date_and_more"),
        ("havasoj", "0019_compdoc_status_compdoc_ubm_delivery_date_and_more"),
        ("hys", "0016_compdoc_status_compdoc_ubm_delivery_date_and_more"),
        ("ozgur", "0022_compdoc_status_compdoc_ubm_delivery_date_and_more"),
        ("piku", "0026_compdoc_status_compdoc_ubm_delivery_date_and_more"),
    ]

    operations = [migrations.RunPython(backfill_workflow_fields, migrations.RunPython.noop)]
