"""DocProof integration endpoints."""

import logging

from requests.exceptions import HTTPError, RequestException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from docproof.client import (  # noqa: F401
    DOCPROOF_URL,
    REQUEST_TIMEOUT_SECONDS,
    find_document_issue,
    find_latest_edms_object_id,
    login,
    normalize_document_number,
    search_issue_number,
)

LOGGER = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search(request):
    """Search DocProof and return the published issue number for a document."""
    document_number = request.query_params.get("document_no")
    if not document_number:
        return Response({"detail": "Document number required."}, status=400)
    return search_response(normalize_document_number(document_number))


def search_response(document_number: str) -> Response:
    """Build the existing DocProof search API response."""
    try:
        issue_number, failure_reason = _search_with_refresh(document_number)
    except RequestException as exception:
        LOGGER.warning("DocProof request failed: %s", exception.__class__.__name__)
        return error_response(
            "DocProof could not be reached.",
            code="DOCPROOF_UNAVAILABLE",
            response_status=503,
        )
    if issue_number is None:
        message = missing_document_message(document_number, failure_reason)
        return Response({"message": message}, status=400)
    return Response(issue_number, status=200)


def _search_with_refresh(document_number):
    try:
        return search_issue_number(document_number)
    except HTTPError:
        LOGGER.info("Retrying DocProof search after refreshing session.")
        login()
        return search_issue_number(document_number)


def missing_document_message(document_number: str, failure_reason: str | None) -> str:
    """Return the legacy user-facing missing document message."""
    if failure_reason == "unpublished":
        return f"Can not find published document in EDMS: {document_number}"
    return f"Can not find or access document: {document_number}"
