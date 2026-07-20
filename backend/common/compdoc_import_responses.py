"""Stable API responses for compliance-document workbook imports."""

from rest_framework import status

from awcenter.api_errors import error_response

from .compdoc_import_audit import fail_import_audit


def import_limit_response(audit, error):
    """Record and return a deterministic workbook row-limit failure."""

    audit.total_rows = error.row_count
    audit.save(update_fields=["total_rows"])
    fail_import_audit(audit, error.default_code, str(error.detail))
    return error_response(
        str(error.detail),
        code=error.default_code,
        response_status=status.HTTP_400_BAD_REQUEST,
    )


def database_conflict_response(audit, error):
    """Audit and reject a confirmation whose reviewed database targets changed."""

    fail_import_audit(audit, error.default_code, str(error.detail))
    return error_response(
        str(error.detail),
        code=error.default_code,
        response_status=status.HTTP_409_CONFLICT,
    )


def confirmation_required_response():
    """Require the explicit preview-confirmation handshake."""

    return error_response(
        "Import preview confirmation is required.",
        code="COMPDOC_IMPORT_CONFIRMATION_REQUIRED",
        response_status=status.HTTP_409_CONFLICT,
    )


def confirmation_error_response(error):
    """Return a stable conflict when the reviewed workbook identity is invalid."""

    return error_response(
        error.detail,
        code=error.code,
        response_status=status.HTTP_409_CONFLICT,
    )


def missing_columns_response(audit, missing_columns):
    """Reject a confirmed workbook missing required mapped columns."""

    detail = "Required workbook columns are missing."
    fail_import_audit(audit, "COMPDOC_IMPORT_COLUMNS_MISSING", detail)
    return error_response(
        detail,
        code="COMPDOC_IMPORT_COLUMNS_MISSING",
        errors={"missing_columns": missing_columns},
        response_status=status.HTTP_400_BAD_REQUEST,
    )
