from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

class ReleaseNote(models.Model):
    version = models.CharField(max_length=32, unique=True)  # "1.8.0"
    title = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    published_at = models.DateTimeField(auto_now_add=True)

    # sürüm bazında zorunlu onay istersen
    requires_ack = models.BooleanField(default=False)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return f"{self.version} - {self.title}"


class ReleaseNoteItem(models.Model):
    class ItemType(models.TextChoices):
        FEATURE = "feature", "Feature"
        FIX = "fix", "Fix"
        BREAKING = "breaking", "Breaking"
        INFO = "info", "Info"
        SECURITY = "security", "Security"

    release_note = models.ForeignKey(
        ReleaseNote, on_delete=models.CASCADE, related_name="items"
    )

    item_type = models.CharField(max_length=16, choices=ItemType.choices)
    heading = models.CharField(max_length=200, blank=True, default="")
    body_md = models.TextField()  # markdown
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["release_note", "item_type"]),
        ]

    def __str__(self):
        return f"{self.release_note.version} [{self.item_type}] {self.heading}"


class ReleaseNoteSeen(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="release_notes_seen")
    release_note = models.ForeignKey(ReleaseNote, on_delete=models.CASCADE, related_name="seen_by")

    seen_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("user", "release_note")]
        indexes = [
            models.Index(fields=["user", "release_note"]),
            models.Index(fields=["user", "seen_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} saw {self.release_note_id}"


