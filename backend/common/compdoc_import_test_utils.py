"""Reusable workbook fixtures for compliance-document import tests."""

from io import BytesIO

import pandas as pd
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile


def valid_row(name="Compliance Document", cover_page_no="CP-001"):
    """Return one representative workbook row using human headers."""

    return {
        "Name": name,
        "Panel": "Flight",
        "Responsible": "Reviewer",
        "Status": "Authority Approved",
        "Cat": "1",
        "Moc": "A",
        "Cover Page No": cover_page_no,
        "Cover Page Issue": 1,
        "Tech Doc No": "TD-001",
        "Tech Doc Issue": 1,
    }


def workbook_upload(rows):
    """Return a valid in-memory OOXML workbook upload."""

    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return workbook_upload_bytes(buffer.getvalue())


def workbook_upload_bytes(content):
    """Return a fresh upload stream for exact workbook bytes."""

    return SimpleUploadedFile(
        "compdocs.xlsx",
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def grant_model_permissions(user, model, *actions):
    """Grant selected Django model actions to a test user."""

    content_type = ContentType.objects.get_for_model(model)
    codenames = [f"{action}_{model._meta.model_name}" for action in actions]
    permissions = Permission.objects.filter(content_type=content_type, codename__in=codenames)
    user.user_permissions.add(*permissions)
    for cache_name in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        user.__dict__.pop(cache_name, None)
