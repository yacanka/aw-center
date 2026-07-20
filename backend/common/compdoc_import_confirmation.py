"""Signed preview confirmation for compliance-document imports."""

import re
from dataclasses import dataclass

from django.conf import settings
from django.core import signing

from .compdoc_import_audit import hash_uploaded_file

CONFIRMATION_SALT = "awcenter.compdoc-import-preview.v2"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ImportConfirmationError(Exception):
    """Describe a safe preview-confirmation contract failure."""

    detail: str
    code: str


@dataclass(frozen=True, slots=True)
class VerifiedImportConfirmation:
    """Hold trusted file and database identities from one signed preview."""

    source_sha256: str
    database_fingerprint: str


def create_import_confirmation(uploaded_file, user, model, database_fingerprint):
    """Sign the exact workbook, owner, and project selected during preview."""

    digest = hash_uploaded_file(uploaded_file)
    payload = confirmation_payload(digest, user, model, database_fingerprint)
    return signing.dumps(payload, salt=CONFIRMATION_SALT, compress=True)


def verify_import_confirmation(token, uploaded_file, user, model):
    """Verify a fresh preview token and return the confirmed file digest."""

    if not token:
        raise ImportConfirmationError(
            "Import preview confirmation is required.",
            "COMPDOC_IMPORT_CONFIRMATION_REQUIRED",
        )
    payload = load_confirmation(token)
    digest = hash_uploaded_file(uploaded_file)
    if not matches_confirmation_identity(payload, digest, user, model):
        raise ImportConfirmationError(
            "The workbook no longer matches the reviewed preview.",
            "COMPDOC_IMPORT_PREVIEW_MISMATCH",
        )
    database_fingerprint = payload.get("database_fingerprint")
    if not isinstance(database_fingerprint, str) or not SHA256_PATTERN.fullmatch(
        database_fingerprint
    ):
        raise invalid_preview_error()
    return VerifiedImportConfirmation(digest, database_fingerprint)


def load_confirmation(token):
    """Load one bounded-age signed confirmation without exposing signature details."""

    max_age = max(int(settings.COMPDOC_IMPORT_PREVIEW_TTL_SECONDS), 1)
    try:
        payload = signing.loads(token, salt=CONFIRMATION_SALT, max_age=max_age)
    except (signing.BadSignature, signing.SignatureExpired) as error:
        raise ImportConfirmationError(
            "The import preview expired or is invalid.",
            "COMPDOC_IMPORT_PREVIEW_EXPIRED",
        ) from error
    if not isinstance(payload, dict):
        raise ImportConfirmationError(
            "The import preview expired or is invalid.",
            "COMPDOC_IMPORT_PREVIEW_EXPIRED",
        )
    return payload


def confirmation_payload(digest, user, model, database_fingerprint):
    """Return the minimal signed identity for one reviewed workbook."""

    return {
        "version": 2,
        "sha256": digest,
        "user_id": str(user.pk),
        "model": model._meta.label_lower,
        "database_fingerprint": database_fingerprint,
    }


def matches_confirmation_identity(payload, digest, user, model):
    """Return whether signed identity fields match the current confirmation request."""

    return all(
        (
            payload.get("version") == 2,
            payload.get("sha256") == digest,
            payload.get("user_id") == str(user.pk),
            payload.get("model") == model._meta.label_lower,
        )
    )


def invalid_preview_error():
    """Return one safe error for malformed signed preview payloads."""

    return ImportConfirmationError(
        "The import preview expired or is invalid.",
        "COMPDOC_IMPORT_PREVIEW_EXPIRED",
    )
