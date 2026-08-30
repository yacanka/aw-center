import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0004_cover_page_version"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DoorsImportMapping",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("module_path", models.CharField(max_length=1024)),
                ("mapping", models.JSONField(default=dict)),
                ("source_columns", models.JSONField(default=list)),
                ("successful_at", models.DateTimeField()),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="doors_import_mappings",
                        to="orgs.project",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_doors_import_mappings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-successful_at"],
                "indexes": [
                    models.Index(
                        fields=["project", "successful_at"],
                        name="compliance__project_0750a0_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("project", "module_path"),
                        name="compliance_unique_doors_import_mapping",
                    )
                ],
            },
        ),
    ]
