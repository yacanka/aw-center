"""Encrypted JIRA credentials remembered across AW Center sessions."""

from django.conf import settings
from django.db import models


class JiraSavedToken(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE, related_name="+",
    )
    ciphertext = models.TextField(editable=False)
