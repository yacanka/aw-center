"""Versioned catalog writes and verified access to private template sources."""

import hashlib
from urllib.parse import urlsplit

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from awcenter.database_errors import ContentConflict, retry_content_write
from awcenter.private_files import PrivateFileIntegrityError, open_verified_private_file
from .template_docx import inspect_docx
from .template_issue import read_template_issue
from .template_models import JiraDocumentTemplate


PUBLIC_FIELDS = (
    "id", "name", "project_id", "project_name", "issue_type_id", "issue_type_name",
    "archived", "version", "placeholders", "mapping",
)
IDENTITY_FIELDS = ("project_id", "project_name", "issue_type_id", "issue_type_name")
CONFLICT = "JIRA_DOCUMENT_TEMPLATE_CHANGED"


def jira_server_id():
    """Distinguish installations while tolerating equivalent origin spellings."""
    url = urlsplit(settings.JIRA_URL)
    port = url.port or {"https": 443, "http": 80}.get(url.scheme)
    identity = (url.scheme, url.hostname or "", str(port), url.path.rstrip("/"))
    return hashlib.sha256("\0".join(identity).encode()).hexdigest()


def read_source(template):
    try:
        with open_verified_private_file(template.source_file, template.source_sha256) as handle:
            return handle.read()
    except (PrivateFileIntegrityError, OSError) as error:
        raise APIException("Stored template could not be verified.", code="TEMPLATE_SOURCE_INVALID") from error


def inspect_template(data):
    fields = inspect_docx(data)
    if not fields:
        raise ValidationError({"detail": "Add at least one {{field}} to the Word template."})
    return fields


def verified_mapping(user, inputs, placeholders, previous_mapping):
    """Only fields visible on the live example may be published as mappings."""
    if not inputs.get("issue"):
        raise ValidationError({"detail": "Load an example JIRA issue to verify the mapping."})
    issue = read_template_issue(user, inputs["issue"])
    names = {field["name"] for field in placeholders}
    retained = {name: field for name, field in previous_mapping.items() if name in names}
    mapping = inputs.get("mapping", retained)
    allowed = {item["id"] for item in issue["fields"] if item["supported"]}
    if not isinstance(mapping, dict) or any(
        name not in names or not isinstance(field, str) or field not in allowed
        for name, field in mapping.items()
    ):
        raise ValidationError({"detail": "Reload the fields and select a supported JIRA field for each mapping."})
    identity = {key: issue[key] for key in IDENTITY_FIELDS}
    return {**identity, "mapping": mapping, "server_id": jira_server_id()}


def save_template(user, inputs, upload, current=None):
    """Validate the live example outside the database transaction, then compare and swap."""
    template = current or JiraDocumentTemplate(created_by=user)
    if current and current.version != inputs["version"]:
        raise ContentConflict(CONFLICT)
    changes = {key: inputs[key] for key in ("name", "archived") if key in inputs}
    content = upload.read() if upload is not None else None
    if content is not None:
        changes["placeholders"] = inspect_template(content)
        changes["source_sha256"] = hashlib.sha256(content).hexdigest()
    if content is not None or "mapping" in inputs or "issue" in inputs:
        fields = changes.get("placeholders", template.placeholders)
        changes.update(verified_mapping(user, inputs, fields, template.mapping))
    if not changes:
        raise ValidationError({"detail": "Provide a change to save."})

    previous = template.source_file.name
    storage = template.source_file.storage
    if content is not None:
        template.source_file.save("source.docx", ContentFile(content), save=False)
        changes["source_file"] = template.source_file.name
    changes.update(updated_by=user, updated_at=timezone.now())

    def persist():
        if not current:
            for key, value in changes.items():
                setattr(template, key, value)
            template.save(force_insert=True)
            return template
        changed = JiraDocumentTemplate.objects.filter(pk=template.pk, version=inputs["version"]).update(
            **changes, version=inputs["version"] + 1
        )
        if not changed:
            raise ContentConflict(CONFLICT)
        if content is not None:
            transaction.on_commit(lambda: storage.delete(previous), robust=True)
        return JiraDocumentTemplate.objects.get(pk=template.pk)

    try:
        return retry_content_write(persist, conflict_code=CONFLICT)
    except Exception:
        if content is not None:
            storage.delete(changes["source_file"])
        raise
