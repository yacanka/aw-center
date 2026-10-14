from django.db import migrations


PROJECTS = (
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


def seed_compliance_projects(apps, schema_editor):
    Project = apps.get_model("orgs", "Project")
    projects = Project.objects.using(schema_editor.connection.alias)
    for slug, name in PROJECTS:
        projects.get_or_create(slug=slug, defaults={"name": name, "enabled": True})
    # Preserve customized names, IDs, documents and role assignments.
    projects.filter(slug="gokbey", name="Gokbey").update(name="Gökbey")


class Migration(migrations.Migration):
    dependencies = [("orgs", "0006_allow_text_ata")]
    operations = [migrations.RunPython(seed_compliance_projects, migrations.RunPython.noop)]
