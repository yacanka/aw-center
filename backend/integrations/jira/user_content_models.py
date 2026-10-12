"""User-created JIRA lists, independent from display preferences."""

from django.conf import settings
from django.db import models


class JiraUserContent(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              primary_key=True, related_name="jira_content")
    subtask_lists = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
