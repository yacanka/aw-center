"""DRF upload orchestration for audited CompDoc imports."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from awcenter.api_errors import error_response
from awcenter.file_security import EXCEL_POLICY, validate_request_upload

from .compdoc_import_confirmation import (
    ImportConfirmationError,
    create_import_confirmation,
    verify_import_confirmation,
)
from .compdoc_import_audit import (
    complete_import_audit,
    fail_import_audit,
    record_import_mapping,
    start_import_audit,
)
from .compdoc_import_pipeline import (
    CompDocImportDatabaseConflict,
    CompDocImportLimitExceeded,
    execute_import,
    prepare_import,
    preview_import,
)
from .compdoc_permissions import CompDocImportPermissions
from .compdoc_import_responses import (
    confirmation_error_response,
    confirmation_required_response,
    database_conflict_response,
    import_limit_response,
    missing_columns_response,
)

logger = logging.getLogger(__name__)


def upload_compdoc_factory(model, serializer_class, view_permission_classes):
    """Return a project-specific audited CompDoc upload API view."""

    class UploadCompDoc(APIView):
        """Preview and execute one project workbook import."""

        queryset = model.objects.none()
        permission_classes = [*view_permission_classes, CompDocImportPermissions]

        def post(self, request):
            """Preview mappings or execute a confirmed audited import."""

            uploaded_file = validate_request_upload(request, "file", EXCEL_POLICY)
            if request.query_params.get("preview") == "true":
                return preview_response(request, uploaded_file, model, serializer_class)
            if request.query_params.get("confirm_import") != "true":
                return confirmation_required_response()
            return confirmed_import_response(request, uploaded_file, model, serializer_class)

    return UploadCompDoc


def preview_response(request, uploaded_file, model, serializer_class):
    """Return mappings, action impact, failures, and an exact-file confirmation."""

    prepared = prepare_import(uploaded_file, model)
    result, database_fingerprint = preview_import(prepared, model, serializer_class)
    confirmation = create_import_confirmation(
        uploaded_file, request.user, model, database_fingerprint
    )
    return Response(
        {
            **prepared.preview,
            **{key: result[key] for key in count_keys()},
            "invalid_documents": public_errors(result["errors"]),
            "confirmation_token": confirmation,
            "database_state_protected": True,
        },
        status=status.HTTP_200_OK,
    )


def confirmed_import_response(request, uploaded_file, model, serializer_class):
    """Execute one confirmed import and always terminate its audit."""

    try:
        confirmation = verify_import_confirmation(
            request.data.get("confirmation_token"), uploaded_file, request.user, model
        )
    except ImportConfirmationError as error:
        return confirmation_error_response(error)
    audit = start_import_audit(
        request, model, uploaded_file, confirmation.source_sha256
    )
    try:
        prepared = prepare_import(uploaded_file, model)
        record_import_mapping(audit, prepared.preview, len(prepared.dataframe))
        if prepared.preview["missing_columns"]:
            return missing_columns_response(audit, prepared.preview["missing_columns"])
        result = execute_import(
            prepared, model, serializer_class, confirmation.database_fingerprint
        )
        complete_import_audit(audit, result)
        return successful_import_response(audit, result)
    except CompDocImportDatabaseConflict as error:
        return database_conflict_response(audit, error)
    except CompDocImportLimitExceeded as error:
        return import_limit_response(audit, error)
    except Exception as error:
        return unexpected_import_response(audit, error)


def unexpected_import_response(audit, error):
    """Log a safe failure identity and terminate its audit."""

    logger.error(
        "CompDoc import failed audit_id=%s failure_type=%s",
        audit.id,
        error.__class__.__name__,
    )
    fail_import_audit(audit, "COMPDOC_IMPORT_FAILED", "Workbook processing failed.")
    return error_response(
        "The workbook could not be processed.",
        code="COMPDOC_IMPORT_FAILED",
        response_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def successful_import_response(audit, result):
    """Return audit identity, counters, and safe row failures."""

    message = (
        f"Import completed: {result['created_count']} created, "
        f"{result['updated_count']} updated, {result['unchanged_count']} unchanged, "
        f"{result['rejected_count']} rejected."
    )
    return Response(
        {
            "message": message,
            "audit_id": audit.id,
            "status": audit.status,
            **{key: result[key] for key in count_keys()},
            "invalid_documents": public_errors(result["errors"]),
        },
        status=status.HTTP_201_CREATED,
    )


def public_errors(errors):
    """Adapt sanitized audit errors to the existing upload UI contract."""

    return [
        {
            **error,
            "error": error.get("fields", error.get("detail")),
            "error_text": error.get("error_text", error.get("detail")),
        }
        for error in errors
    ]


def count_keys():
    """Return stable import result counter names."""

    return ("created_count", "updated_count", "unchanged_count", "rejected_count")
