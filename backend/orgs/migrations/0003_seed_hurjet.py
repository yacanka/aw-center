from django.db import migrations


def seed_hurjet(apps, schema_editor):
    Project = apps.get_model("orgs", "Project")
    Project.objects.get_or_create(
        slug="hurjet",
        defaults={"name": "Hürjet", "enabled": True},
    )


class Migration(migrations.Migration):
    dependencies = [("orgs", "0002_seed_projects")]
    operations = [migrations.RunPython(seed_hurjet, migrations.RunPython.noop)]
