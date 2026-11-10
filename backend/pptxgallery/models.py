from pathlib import Path

from django.conf import settings
from django.db import models

from jobs.storage import private_job_storage


def presentation_source_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"presentations/{instance.owner_id}/{instance.id}/source{suffix}"


def slide_image_path(instance, _filename):
    return (
        f"presentations/{instance.presentation.owner_id}/"
        f"{instance.presentation_id}/slides/{instance.index}.png"
    )


def slide_thumb_path(instance, _filename):
    return (
        f"presentations/{instance.presentation.owner_id}/"
        f"{instance.presentation_id}/thumbs/{instance.index}.png"
    )


class Presentation(models.Model):
    """An owned presentation whose source and slides remain private."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="presentations",
    )
    title = models.CharField(max_length=255)
    file = models.FileField(
        storage=private_job_storage,
        upload_to=presentation_source_path,
        max_length=500,
    )
    source_name = models.CharField(max_length=180)
    source_sha256 = models.CharField(max_length=64)
    conversion_job = models.ForeignKey(
        "jobs.Job",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="presentation_conversions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=32,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("converting", "Converting"),
            ("ready", "Ready"),
            ("failed", "Failed"),
        ],
    )

    class Meta:
        ordering = ["-created_at", "title", "id"]

    def __str__(self):
        return self.title


class Slide(models.Model):
    """One private, integrity-fingerprinted presentation slide."""

    presentation = models.ForeignKey(
        Presentation,
        related_name="slides",
        on_delete=models.CASCADE,
    )
    index = models.PositiveIntegerField()
    image = models.ImageField(
        storage=private_job_storage,
        upload_to=slide_image_path,
        max_length=500,
    )
    image_sha256 = models.CharField(max_length=64)
    thumb = models.ImageField(
        storage=private_job_storage,
        upload_to=slide_thumb_path,
        max_length=500,
        blank=True,
    )
    thumb_sha256 = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["presentation", "index"],
                name="pptxgallery_unique_presentation_slide",
            )
        ]
        ordering = ["index"]

    def __str__(self):
        return f"{self.presentation.title} - Slide {self.index}"
