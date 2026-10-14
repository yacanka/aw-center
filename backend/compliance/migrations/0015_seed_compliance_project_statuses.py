from django.db import migrations


def seed_project_statuses(apps, schema_editor):
    Project = apps.get_model("orgs", "Project")
    Status = apps.get_model("compliance", "DocumentStatus")
    alias = schema_editor.connection.alias
    slugs = (
        "havasoj_stc1", "havasoj_stc2", "hyeu", "hurkus_aviyonik",
        "hjt", "hsp", "navy", "bkm", "mmu",
    )
    for project_id in Project.objects.using(alias).filter(slug__in=slugs).values_list("pk", flat=True):
        Status.objects.using(alias).get_or_create(
            project_id=project_id, value="unknown", defaults={"label": "Unknown"},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orgs", "0007_seed_compliance_projects"),
        ("compliance", "0014_compliancedocument_ubm_revised_target_date_and_more"),
    ]
    operations = [migrations.RunPython(seed_project_statuses, migrations.RunPython.noop)]
