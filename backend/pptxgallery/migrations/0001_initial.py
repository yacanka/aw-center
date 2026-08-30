import django.db.models.deletion
import jobs.storage
import pptxgallery.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("jobs", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Presentation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                (
                    "file",
                    models.FileField(
                        max_length=500,
                        storage=jobs.storage.PrivateJobStorage(),
                        upload_to=pptxgallery.models.presentation_source_path,
                    ),
                ),
                ("source_name", models.CharField(max_length=180)),
                ("source_sha256", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("converting", "Converting"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                (
                    "conversion_job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="presentation_conversions",
                        to="jobs.job",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="presentations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "title", "id"]},
        ),
        migrations.CreateModel(
            name="Slide",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("index", models.PositiveIntegerField()),
                (
                    "image",
                    models.ImageField(
                        max_length=500,
                        storage=jobs.storage.PrivateJobStorage(),
                        upload_to=pptxgallery.models.slide_image_path,
                    ),
                ),
                ("image_sha256", models.CharField(max_length=64)),
                (
                    "thumb",
                    models.ImageField(
                        blank=True,
                        max_length=500,
                        storage=jobs.storage.PrivateJobStorage(),
                        upload_to=pptxgallery.models.slide_thumb_path,
                    ),
                ),
                ("thumb_sha256", models.CharField(blank=True, max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "presentation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slides",
                        to="pptxgallery.presentation",
                    ),
                ),
            ],
            options={
                "ordering": ["index"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("presentation", "index"),
                        name="pptxgallery_unique_presentation_slide",
                    )
                ],
            },
        ),
    ]
