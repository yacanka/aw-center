"""Every initially seeded project starts with the protected Unknown status."""

from django.db import migrations


def seed_default_statuses(apps, schema_editor):
    alias = schema_editor.connection.alias
    projects = apps.get_model("orgs", "Project").objects.using(alias)
    statuses = apps.get_model("compliance", "DocumentStatus").objects.using(alias)
    for project_id in projects.values_list("pk", flat=True).iterator():
        statuses.get_or_create(
            project_id=project_id, value="unknown", defaults={"label": "Unknown"},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0002_initial"),
        ("orgs", "0002_seed_projects"),
    ]
    operations = [migrations.RunPython(seed_default_statuses, migrations.RunPython.noop)]
