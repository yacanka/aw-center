"""Make Dashboard User available through existing account role administration."""

from django.db import migrations


def seed_dashboard_user(apps, schema_editor):
    group = apps.get_model("auth", "Group")
    group.objects.using(schema_editor.connection.alias).get_or_create(name="Dashboard User")


class Migration(migrations.Migration):
    dependencies = [("users", "0002_email_identity_guard")]
    operations = [migrations.RunPython(seed_dashboard_user, migrations.RunPython.noop)]
