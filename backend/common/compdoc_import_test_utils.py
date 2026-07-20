"""Reusable workbook fixtures for compliance-document import tests."""

from io import BytesIO

import pandas as pd
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
