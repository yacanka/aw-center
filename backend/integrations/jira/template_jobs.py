"""Create owner-scoped document jobs from a frozen template and live JIRA fields."""

import hashlib
import json
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, ValidationError

from awcenter.private_files import PrivateFileIntegrityError, open_verified_private_file
from jobs.api import job_creation_response
from jobs.artifacts import remove_temporary_artifact, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult
from jobs.execution import update_progress
from jobs.services import (
    IdempotencyConflict, calculate_upload_sha256, find_idempotent_job, persist_job, record_event,
    require_idempotency_key,
)

from .template_catalog import jira_server_id, read_source
from .template_docx import INVALID_XML_CHAR, MAX_FIELDS, MAX_VALUE_LENGTH, render_docx
from .template_issue import ISSUE_KEY, read_template_issue, template_issue_key
from .template_models import JiraDocumentTemplate


JOB_KIND = "jira.create_template_document"


class TemplateChanged(APIException):
    status_code = 409
    default_code = "JIRA_DOCUMENT_TEMPLATE_CHANGED"
    default_detail = "Reload the issue and choose a current, matching template."


class GenerationInputs(serializers.Serializer):
    issue = serializers.CharField(max_length=2048)
    template_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    manual_values = serializers.JSONField(default=dict)

    def validate_manual_values(self, values):
        if not isinstance(values, dict) or len(values) > MAX_FIELDS:
            raise ValidationError("Provide a text value for each manual field.")
        for value in values.values():
            if not isinstance(value, str) or len(value) > MAX_VALUE_LENGTH or INVALID_XML_CHAR.search(value):
                raise ValidationError("The manual field text is invalid or exceeds the field limit.")
        return values


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _replay(job, parameters):
    if job.parameters != parameters:
        raise IdempotencyConflict()
    return job_creation_response(job, False)


def generate_template_job(request):
    """Replays identify the caller's request independently of subsequent source changes."""

    key = require_idempotency_key(request.headers.get("Idempotency-Key", ""))
    serializer = GenerationInputs(data=request.data)
    serializer.is_valid(raise_exception=True)
    inputs = serializer.validated_data
    reference = template_issue_key(inputs["issue"])
    manual = inputs["manual_values"]
    parameters = {
        "issue": reference, "template_id": str(inputs["template_id"]), "version": inputs["version"],
        "manual_sha256": hashlib.sha256(_json_bytes(manual)).hexdigest(),
    }
    existing = find_idempotent_job(request.user, JOB_KIND, key)
    if existing:
        return _replay(existing, parameters)
    issue = read_template_issue(request.user, reference)
    return _enqueue(request, key, parameters, issue, manual)


def _enqueue(request, key, parameters, issue, manual):
    # JIRA was read outside the transaction. Lock before checking version and reading the
    # file so a concurrent publisher cannot replace or retire it until the enqueue commits.
    job, created = None, False
    try:
        with transaction.atomic():
            template = JiraDocumentTemplate.objects.select_for_update().filter(pk=parameters["template_id"]).first()
            existing = find_idempotent_job(request.user, JOB_KIND, key)
            if existing:
                return _replay(existing, parameters)
            if template is None:
                raise NotFound("The document template is unavailable.")
            _verify_selection(template, parameters["version"], issue)
            upload = _snapshot(template, issue, manual)
            job, created = persist_job(
                request.user, JOB_KIND, f"Create document for {issue['issue']}", parameters,
                upload, calculate_upload_sha256(upload), key, getattr(request, "request_id", ""),
            )
            if not created:
                return _replay(job, parameters)
            record_event(job, "Job queued.")
    except Exception:
        if created:
            job.input_file.delete(save=False)
        raise
    return job_creation_response(job, True)


def _verify_selection(template, version, issue):
    if (template.archived or template.version != version or template.server_id != jira_server_id()
            or template.project_id != issue["project_id"] or template.issue_type_id != issue["issue_type_id"]):
        raise TemplateChanged()


def _resolved_values(template, issue, manual):
    fields = {row["id"]: row for row in issue["fields"]}
    names = {item["name"] for item in template.placeholders}
    if manual.keys() - (names - template.mapping.keys()):
        raise ValidationError("Only unmapped template fields accept manual values.")
    values = {name: manual.get(name, "") for name in names}
    for name, field_id in template.mapping.items():
        field = fields.get(field_id)
        if name not in names or field is None or not field["supported"]:
            raise TemplateChanged("A mapped JIRA field is unavailable. Ask the publisher to review the mapping.")
        values[name] = field["value"]
    return values


def _snapshot(template, issue, manual):
    manifest = {
        "schema": 1, "issue": issue["issue"], "server_id": template.server_id,
        "project_id": template.project_id, "issue_type_id": template.issue_type_id,
        "template_id": str(template.pk), "version": template.version,
        "source_sha256": template.source_sha256, "mapping": template.mapping,
        "values": _resolved_values(template, issue, manual),
    }
    metadata = _json_bytes(manifest)
    if len(metadata) > settings.JOB_JSON_MAX_INPUT_BYTES:
        raise ValidationError("The resolved template fields exceed the snapshot size limit.")
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", metadata)
        archive.writestr("template.docx", read_source(template))
    return ContentFile(buffer.getvalue(), name="document-snapshot.zip")


def _read_snapshot(job):
    """Read only server-generated, SHA-256 verified entries; never extract archive paths."""

    try:
        with open_verified_private_file(job.input_file, job.input_sha256) as source, ZipFile(source) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            template = archive.read("template.docx")
        if (manifest["schema"] != 1 or not ISSUE_KEY.fullmatch(manifest["issue"])
                or hashlib.sha256(template).hexdigest() != manifest["source_sha256"]):
            raise ValueError
        return template, manifest["issue"], manifest["values"]
    except (KeyError, ValueError, TypeError, OSError, PrivateFileIntegrityError, BadZipFile):
        raise JobExecutionFailure("The private document snapshot is invalid.", "JOB_INPUT_CORRUPT") from None


def execute_template_document(job):
    """Render using only the verified snapshot under the worker's current execution lease."""

    update_progress(job.id, 10, "Verifying document snapshot.")
    template, issue, values = _read_snapshot(job)
    try:
        output = render_docx(template, values)
    except ValidationError:
        raise JobExecutionFailure("The saved template could not render these fields.", "JIRA_TEMPLATE_RENDER_FAILED") from None
    update_progress(job.id, 90, "Document rendered.")
    path = temporary_output(".docx")
    try:
        path.write_bytes(output)
        return JobExecutionResult(path, f"{issue}.docx", "Document created.", {"issue": issue})
    except Exception:
        remove_temporary_artifact(path)
        raise
