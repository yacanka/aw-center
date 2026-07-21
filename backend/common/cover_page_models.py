import uuid

from django.db import models
from simple_history.models import HistoricalRecords


class CoverPage(models.Model):
    """Represent one project-scoped cover page shared by compliance documents."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_slug = models.CharField(max_length=64)
    number = models.CharField(max_length=32)
    issue = models.CharField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["project_slug", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["project_slug", "number"],
                name="common_unique_project_cover_page",
            ),
        ]

    def __str__(self):
        return f"{self.project_slug}: {self.number}"
