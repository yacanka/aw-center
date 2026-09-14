"""Read Numarator input contracts through the credential-bearing local worker."""

import json

from django.core.files.base import ContentFile
from rest_framework import serializers

from integrations.numarator.client import (
    NumaratorClient, NumaratorError, NumaratorTemporaryError,
    credential_fingerprint, is_configured, project_format_codes,
)
from jobs.artifacts import temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult
from jobs.execution import update_progress
from jobs.services import create_job
from orgs.access_policy import has_project_role
from orgs.models import Project, ProjectRoleAssignment

from .numbering import NumaratorUnavailable


def create_numbering_format_job(*, project, actor, format_code, operation_id, request_id=""):
    if not is_configured(project.slug):
        raise NumaratorUnavailable()
    if format_code not in project_format_codes(project.slug):
        raise serializers.ValidationError({"format_code": "Select an allowed format."})
    parameters = {
        "project_slug": project.slug,
        "format_code": format_code,
        "credential_fingerprint": credential_fingerprint(),
    }
    job, _created = create_job(
        owner=actor,
        kind="compliance.describe_numbering_format",
        title=f"Read number format · {project.slug}"[:160],
        parameters=parameters,
        uploaded_file=ContentFile(json.dumps(parameters).encode(), name="number-format.json"),
        idempotency_key=f"numarator-format:{operation_id}",
        request_id=request_id,
    )
    return job


def execute_numbering_format_description(job):
    parameters = job.parameters
    project = Project.objects.filter(slug=parameters.get("project_slug"), enabled=True).first()
    if not project or not job.owner.is_active or not has_project_role(
        job.owner, project, ProjectRoleAssignment.Domain.COMPLIANCE,
        ProjectRoleAssignment.Role.EDITOR,
    ):
        raise JobExecutionFailure("Project access is required.", "PROJECT_ROLE_REQUIRED")
    format_code = parameters.get("format_code")
    if (
        not is_configured(project.slug, require_credential=True)
        or parameters.get("credential_fingerprint") != credential_fingerprint()
        or format_code not in project_format_codes(project.slug)
    ):
        raise JobExecutionFailure("Numarator configuration changed.", "NUMARATOR_NOT_CONFIGURED")
    update_progress(job.id, 10, "Loading number format fields.")
    client = None
    try:
        client = NumaratorClient()
        contract = client.describe_format(format_code)
    except NumaratorError as error:
        raise JobExecutionFailure(
            "Number format fields could not be loaded from Numarator.",
            "NUMARATOR_FORMAT_UNAVAILABLE", isinstance(error, NumaratorTemporaryError),
        ) from error
    finally:
        if client is not None:
            client.close()
    update_progress(job.id, 90, "Number format fields loaded.")
    output = temporary_output(".json")
    output.write_text(json.dumps({"schema_version": 1, **contract}), encoding="utf-8")
    return JobExecutionResult(output, "number-format.json", "Number format fields loaded.")


def validate_format_context(contract, values):
    """Reject missing/oversized fields before requesting an external number."""
    for field in contract["fields"]:
        value = values.get(field["key"])
        if field["required"] and (value is None or not str(value).strip()):
            raise JobExecutionFailure(
                "Complete the required number format fields.", "NUMARATOR_CONTEXT_INVALID",
            )
        if value is not None and len(str(value)) > field["max_length"]:
            raise JobExecutionFailure(
                "A number format value exceeds its allowed length.", "NUMARATOR_CONTEXT_INVALID",
            )
