"""Bind legacy revision deduplication to the document number at rollout.

Old hashes do not retain their evidence or original number. Conservatively bind
all existing revision history to the current number, preserving suppression and
pending delivery identities. Deploy with notification workers stopped/restarted.
"""

import hashlib

from django.db import migrations


def bind_revision_numbers(apps, schema_editor):
    logs = apps.get_model("compliance", "NotificationLog").objects.using(
        schema_editor.connection.alias,
    )
    # Only deduplication changes. In particular, never rotate Message-ID or a
    # pending/claimed delivery's lease and outcome during this forward migration.
    last_id = None
    while True:
        page = logs.filter(event_type="revision_available").order_by("pk")
        if last_id is not None:
            page = page.filter(pk__gt=last_id)
        batch = list(page.values_list("pk", "event_key", "profile__document__number")[:500])
        if not batch:
            return
        for log_id, legacy_key, number in batch:
            event_key = hashlib.sha256(f"{legacy_key}:{(number or '').strip()}".encode()).hexdigest()
            logs.filter(pk=log_id).update(event_key=event_key)
        last_id = batch[-1][0]


class Migration(migrations.Migration):
    dependencies = [("compliance", "0003_seed_default_statuses")]
    operations = [migrations.RunPython(bind_revision_numbers)]
