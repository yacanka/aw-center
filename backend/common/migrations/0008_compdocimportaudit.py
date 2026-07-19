import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0007_delete_tempcompdoc"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompDocImportAudit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("project_slug", models.CharField(db_index=True, max_length=64)),
                ("source_filename", models.CharField(max_length=255)),
                ("source_size", models.PositiveBigIntegerField(default=0)),
                ("source_sha256", models.CharField(editable=False, max_length=64)),
                ("imported_by_username", models.CharField(max_length=150)),
                ("request_id", models.CharField(blank=True, max_length=64)),
                ("header_row", models.PositiveSmallIntegerField(null=True)),
                ("mapped_columns", models.JSONField(default=list)),
                ("unmapped_columns", models.JSONField(default=list)),
                ("missing_columns", models.JSONField(default=list)),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("created_count", models.PositiveIntegerField(default=0)),
                ("updated_count", models.PositiveIntegerField(default=0)),
                ("rejected_count", models.PositiveIntegerField(default=0)),
                ("error_summary", models.JSONField(default=list)),
                ("status", models.CharField(choices=[("processing", "Processing"), ("success", "Success"), ("partial", "Partial"), ("failed", "Failed")], db_index=True, default="processing", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(null=True)),
                ("duration_ms", models.PositiveIntegerField(null=True)),
                ("imported_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="compdoc_import_audits", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.AddIndex(
            model_name="compdocimportaudit",
            index=models.Index(fields=["project_slug", "started_at"], name="common_comp_project_38f175_idx"),
        ),
    ]
