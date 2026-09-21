from django.db import migrations


def seed_dcc_projects(apps, schema_editor):
    Project = apps.get_model("orgs", "Project")
    projects = Project.objects.using(schema_editor.connection.alias)
    for slug, name in (
        ("gokbey_jandarma", "Gökbey Jandarma"),
        ("gokbey_sivil", "Gökbey Sivil"),
        ("hurkus", "Hürkuş"),
    ):
        projects.get_or_create(slug=slug, defaults={"name": name, "enabled": True})
    # Preserve operator-customized names and all existing project relationships.
    projects.filter(slug="ozgur", name="Ozgur").update(name="Özgür")


class Migration(migrations.Migration):
    dependencies = [("orgs", "0003_seed_hurjet")]
    operations = [migrations.RunPython(seed_dcc_projects, migrations.RunPython.noop)]
