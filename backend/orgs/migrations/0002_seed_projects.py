from django.db import migrations


PROJECTS = (
    ("ozgur", "Ozgur"),
    ("piku", "Piku"),
    ("aesa", "AESA"),
    ("havasoj", "Havasoj"),
    ("hys", "HYS"),
    ("blok30", "Blok 30"),
    ("blok4050", "Blok 40/50"),
    ("gokbey", "Gokbey"),
)


def seed_projects(apps, schema_editor):
    Project = apps.get_model("orgs", "Project")
    Project.objects.bulk_create(
        [Project(slug=slug, name=name, enabled=True) for slug, name in PROJECTS]
    )


class Migration(migrations.Migration):
    dependencies = [("orgs", "0001_initial")]
    operations = [migrations.RunPython(seed_projects, migrations.RunPython.noop)]
