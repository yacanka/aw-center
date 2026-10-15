"""Initial business project catalog; keep aligned with the technical registry."""

from django.db import migrations


PROJECTS = (
    ("ozgur", "Özgür"),
    ("piku", "Piku"),
    ("aesa", "AESA"),
    ("havasoj", "Havasoj"),
    ("hys", "HYS"),
    ("blok30", "Blok 30"),
    ("blok4050", "Blok 40/50"),
    ("gokbey", "Gökbey"),
    ("hurjet", "Hürjet"),
    ("gokbey_jandarma", "Gökbey Jandarma"),
    ("gokbey_sivil", "Gökbey Sivil"),
    ("hurkus", "Hürkuş"),
    ("havasoj_stc1", "Havasoj STC1"),
    ("havasoj_stc2", "Havasoj STC2"),
    ("hyeu", "HYEU"),
    ("hurkus_aviyonik", "Hürkuş Aviyonik"),
    ("hjt", "HJT"),
    ("hsp", "HSP"),
    ("navy", "Navy"),
    ("bkm", "BKM"),
    ("mmu", "MMU"),
)


def seed_projects(apps, schema_editor):
    projects = apps.get_model("orgs", "Project").objects.using(schema_editor.connection.alias)
    for slug, name in PROJECTS:
        projects.get_or_create(slug=slug, defaults={"name": name, "enabled": True})


class Migration(migrations.Migration):
    dependencies = [("orgs", "0001_initial")]
    operations = [migrations.RunPython(seed_projects, migrations.RunPython.noop)]
