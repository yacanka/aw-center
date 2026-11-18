"""Centrally published DOCX templates indexed by native JIRA identities."""

import uuid

from django.conf import settings
from django.db import models

from jobs.storage import private_job_storage


def template_source_path(template, _filename):
    return f"jira-document-templates/{template.id}/{uuid.uuid4().hex}.docx"


class JiraDocumentTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    server_id = models.CharField(max_length=64)
    project_id = models.CharField(max_length=128)
    project_name = models.CharField(max_length=255)
    issue_type_id = models.CharField(max_length=128)
    issue_type_name = models.CharField(max_length=255)
    source_file = models.FileField(storage=private_job_storage, upload_to=template_source_path)
    source_sha256 = models.CharField(max_length=64)
    placeholders = models.JSONField(default=list)
    mapping = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        indexes = [models.Index(fields=("server_id", "project_id", "issue_type_id", "archived"),
                                name="jira_doc_template_match")]
        permissions = [("manage_jira_document_templates", "Publish central JIRA document templates")]
