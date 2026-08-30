"""DOORS module sources adapted to the canonical compliance import pipeline."""

import hashlib
import json
import re

from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from awcenter.private_files import PrivateFileIntegrityError, open_verified_private_file

from .compdoc_import import get_missing_required_fields, map_headers
from .imports import (
    IMPORT_FIELDS,
    SHA256_PATTERN,
    execute_source_plan,
    plan_fingerprint,
    prepare_tabular_plan,
)
from .models import DoorsImportMapping, ImportAudit


DOORS_CONFIRMATION_SALT = "awcenter.compliance-doors-import.v1"
MAX_DOORS_COLUMNS = 50


def load_doors_source(job):
    """Read and validate one owner-scoped, integrity-checked DOORS export artifact."""

    if not job.output_file or not SHA256_PATTERN.fullmatch(str(job.output_sha256 or "")):
        raise ValidationError(
            {"job_id": "The DOORS export output is unavailable."},
            code="DOORS_IMPORT_SOURCE_UNAVAILABLE",
        )
    try:
        with open_verified_private_file(job.output_file, job.output_sha256) as output:
            payload = json.load(output)
    except (OSError, UnicodeError, json.JSONDecodeError, PrivateFileIntegrityError) as error:
        raise ValidationError(
            {"job_id": "The DOORS export output failed integrity validation."},
            code="DOORS_IMPORT_SOURCE_INVALID",
        ) from error

    if (
        not isinstance(payload, dict)
        or payload.get("type") != "doors_module_export"
        or payload.get("schema_version") != 1
    ):
        raise _invalid_source()
    module_path = payload.get("module_path")
    columns = payload.get("columns")
    results = payload.get("results")
    if payload.get("truncated") is True:
        raise ValidationError(
            {"job_id": "The DOORS module exceeds the configured import row limit."},
            code="IMPORT_ROW_LIMIT",
        )
    if payload.get("attributes_truncated") is True:
        raise ValidationError(
            {"job_id": "The DOORS module exceeds the 50-field import limit."},
            code="DOORS_IMPORT_COLUMN_LIMIT",
        )
    if not isinstance(module_path, str) or not module_path.strip() or len(module_path) > 1024:
        raise _invalid_source()
    if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_DOORS_COLUMNS:
        raise _invalid_source()
    if any(
        not isinstance(column, str) or not column.strip() or len(column) > 256
        for column in columns
    ):
        raise _invalid_source()
    if len({column.casefold() for column in columns}) != len(columns):
        raise _invalid_source()
    row_limit = max(int(settings.AWCENTER_MAX_COMPDOC_IMPORT_ROWS), 1)
    if (
        not isinstance(results, list)
        or payload.get("count") != len(results)
        or len(results) > row_limit
    ):
        raise ValidationError(
            {"job_id": f"The DOORS export exceeds the {row_limit}-row import limit."},
            code="IMPORT_ROW_LIMIT",
        )

    rows = []
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("attributes"), dict):
            raise _invalid_source()
        attributes = result["attributes"]
        if set(attributes) - set(columns):
            raise _invalid_source()
        if any(isinstance(value, (dict, list)) for value in attributes.values()):
            raise _invalid_source()
        rows.append({column: attributes.get(column) for column in columns})
    return {
        "module_path": module_path.strip(),
        "columns": columns,
        "rows": rows,
    }


def default_mapping(project, source):
    """Return the last successful module mapping or safe first-use suggestions."""

    saved = DoorsImportMapping.objects.filter(
        project=project,
        module_path=source["module_path"],
    ).first()
    candidate = saved.mapping if saved else map_headers(source["columns"], IMPORT_FIELDS)
    return sanitize_mapping(candidate, source["columns"])


def validate_mapping(mapping, columns):
    """Require a one-to-one mapping containing the canonical identity fields."""

    if not isinstance(mapping, dict) or not mapping:
        raise ValidationError({"mapping": "Map at least the required DOORS columns."})
    if any(
        not isinstance(source, str) or not isinstance(target, str)
        for source, target in mapping.items()
    ):
        raise ValidationError({"mapping": "DOORS field mappings must be text pairs."})
    if set(mapping) - set(columns):
        raise ValidationError(
            {"mapping": "A mapped DOORS column is not present in this export."}
        )
    if set(mapping.values()) - IMPORT_FIELDS:
        raise ValidationError({"mapping": "A mapped compliance field is unsupported."})
    if len(set(mapping.values())) != len(mapping):
        raise ValidationError(
            {"mapping": "Each compliance field can be linked only once."}
        )
    missing = get_missing_required_fields(mapping.values(), IMPORT_FIELDS)
    if missing:
        raise ValidationError(
            {"mapping": {field: "This field must be linked." for field in missing}}
        )
    return dict(mapping)


def prepare_doors_plan(job, project, request, mapping, *, lock_existing=False):
    source = load_doors_source(job)
    mapping = validate_mapping(mapping, source["columns"])
    source_rows = tuple(
        (
            index,
            {
                target: source["rows"][index - 1].get(column)
                for column, target in mapping.items()
            },
        )
        for index in range(1, len(source["rows"]) + 1)
    )
    preview_mapping = {
        "header_row": None,
        "mapped_columns": [
            {"source": source_column, "target": target}
            for source_column, target in mapping.items()
        ],
        "unmapped_columns": [
            column for column in source["columns"] if column not in mapping
        ],
        "missing_columns": get_missing_required_fields(mapping.values(), IMPORT_FIELDS),
    }
    return prepare_tabular_plan(
        source_rows,
        project,
        request,
        mapping=preview_mapping,
        lock_existing=lock_existing,
    )


def create_doors_confirmation(job, mapping, user, project, plan):
    return signing.dumps(
        {
            "version": 2,
            "job_id": str(job.pk),
            "sha256": job.output_sha256,
            "mapping_sha256": mapping_fingerprint(mapping),
            "user_id": str(user.pk),
            "project": project.slug,
            "database_fingerprint": plan_fingerprint(plan),
        },
        salt=DOORS_CONFIRMATION_SALT,
        compress=True,
    )


def verify_doors_confirmation(token, job, mapping, user, project):
    if not token:
        raise ValidationError(
            {"confirmation_token": "Import preview confirmation is required."},
            code="IMPORT_CONFIRMATION_REQUIRED",
        )
    try:
        payload = signing.loads(
            token,
            salt=DOORS_CONFIRMATION_SALT,
            max_age=max(int(settings.COMPDOC_IMPORT_PREVIEW_TTL_SECONDS), 1),
        )
    except (signing.BadSignature, signing.SignatureExpired) as error:
        raise ValidationError(
            {"confirmation_token": "Import preview expired or is invalid."},
            code="IMPORT_PREVIEW_EXPIRED",
        ) from error
    identity_matches = all(
        (
            payload.get("version") == 2,
            payload.get("job_id") == str(job.pk),
            payload.get("sha256") == job.output_sha256,
            payload.get("mapping_sha256") == mapping_fingerprint(mapping),
            payload.get("user_id") == str(user.pk),
            payload.get("project") == project.slug,
            SHA256_PATTERN.fullmatch(str(payload.get("database_fingerprint", ""))),
        )
    )
    if not identity_matches:
        raise ValidationError(
            {
                "confirmation_token": (
                    "DOORS source or mapping does not match the reviewed preview."
                )
            },
            code="IMPORT_PREVIEW_MISMATCH",
        )
    return payload["database_fingerprint"]


def execute_doors_plan(job, mapping, project, request, expected_fingerprint):
    source = load_doors_source(job)
    audit, plan = execute_source_plan(
        project,
        request,
        expected_fingerprint,
        prepare_locked=lambda: prepare_doors_plan(
            job,
            project,
            request,
            mapping,
            lock_existing=True,
        ),
        audit_values={
            "source_filename": _source_name(source["module_path"]),
            "source_size": max(int(job.output_file.size or 0), 0),
            "source_sha256": job.output_sha256,
        },
    )
    if audit.status == ImportAudit.Status.SUCCESS:
        DoorsImportMapping.objects.update_or_create(
            project=project,
            module_path=source["module_path"],
            defaults={
                "mapping": dict(mapping),
                "source_columns": source["columns"],
                "updated_by": request.user,
                "successful_at": audit.completed_at or timezone.now(),
            },
        )
    return audit, plan


def mapping_fingerprint(mapping):
    encoded = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def sanitize_mapping(mapping, columns):
    result = {}
    used_targets = set()
    for source, target in mapping.items() if isinstance(mapping, dict) else ():
        if source not in columns or target not in IMPORT_FIELDS or target in used_targets:
            continue
        result[source] = target
        used_targets.add(target)
    return result


def _source_name(module_path):
    module_name = re.split(r"[/\\]", module_path)[-1] or "module"
    return f"DOORS - {module_name}"[:255]


def _invalid_source():
    return ValidationError(
        {"job_id": "The DOORS export output has an unsupported format."},
        code="DOORS_IMPORT_SOURCE_INVALID",
    )
