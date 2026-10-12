"""Saved analysis questions are content, rather than appearance settings."""

from django.conf import settings
from django.db import models


class DocumentAnalysisUserContent(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              primary_key=True, related_name="analysis_content")
    checks = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
