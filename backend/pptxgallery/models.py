from django.db import models
from django.utils.text import slugify

class Presentation(models.Model):
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="pptx/")
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=32, default="pending", choices=[
        ("pending", "Pending"), ("converting", "Converting"), ("ready", "Ready"), ("failed", "Failed")
    ])

    def __str__(self):
        return self.title

class Slide(models.Model):
    presentation = models.ForeignKey(Presentation, related_name="slides", on_delete=models.CASCADE)
    index = models.PositiveIntegerField()
    image = models.ImageField(upload_to="slides/")
    thumb = models.ImageField(upload_to="slides/thumbs/", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("presentation", "index")
        ordering = ["index"]

    def __str__(self):
        return f"{self.presentation.title} - Slide {self.index}"