"""Add the AKSUNGUR and İHA projects and their default compliance status."""

from django.db import migrations


def seed_projects(apps, schema_editor):
    alias = schema_editor.connection.alias
    projects = apps.get_model("orgs", "Project").objects.using(alias)
    statuses = apps.get_model("compliance", "DocumentStatus").objects.using(alias)
    for slug, name in (("aksungur", "AKSUNGUR"), ("iha", "İHA")):
        project, _ = projects.get_or_create(slug=slug, defaults={"name": name, "enabled": True})
        statuses.get_or_create(project_id=project.pk, value="unknown", defaults={"label": "Unknown"})


class Migration(migrations.Migration):
    dependencies = [
        ("orgs", "0003_optional_panel_ata"),
        ("compliance", "0004_revision_notification_identity"),
    ]
    operations = [migrations.RunPython(seed_projects, migrations.RunPython.noop)]
