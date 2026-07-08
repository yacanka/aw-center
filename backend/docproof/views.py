"""DocProof integration endpoints."""

import logging
from base64 import b64decode
from binascii import Error as Base64DecodeError
from typing import Any

import requests
from django.conf import settings
from requests import Session
from requests.exceptions import HTTPError, RequestException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

LOGGER = logging.getLogger(__name__)
CERTIFICATE_FILE = settings.CERTIFICATES_DIR / "dmntai_intra.crt"
DOCPROOF_URL = settings.DOCPROOF_URL.rstrip("/")
REQUEST_TIMEOUT_SECONDS = 10
LOGIN_TIMEOUT_SECONDS = 5

session = requests.Session()
session.verify = CERTIFICATE_FILE if CERTIFICATE_FILE.exists() else False


def decode_secret(encoded_secret: str) -> str:
    """Decode a base64-encoded integration secret from settings."""
    return b64decode(encoded_secret).decode("utf-8")


def get_credentials() -> tuple[str, str] | None:
    """Return decoded DocProof credentials when both settings are present."""
    if not settings.AW_USERNAME or not settings.AW_PASSWORD:
        return None
    try:
        return decode_secret(settings.AW_USERNAME), decode_secret(settings.AW_PASSWORD)
    except (Base64DecodeError, UnicodeDecodeError) as exception:
        LOGGER.error("Invalid DocProof credential encoding: %s", exception)
        return None


def login(client: Session = session) -> bool:
    """Authenticate the shared DocProof session without logging secrets."""
    credentials = get_credentials()
    if not credentials:
        LOGGER.warning("DocProof credentials are not configured.")
        return False
    payload = {"j_username": credentials[0], "j_password": credentials[1]}
    try:
        response = client.post(login_url(), data=payload, timeout=LOGIN_TIMEOUT_SECONDS)
        response.raise_for_status()
    except RequestException as exception:
        LOGGER.warning("DocProof login failed: %s", exception)
        return False
    return True


def login_url() -> str:
    """Return the DocProof login endpoint URL."""
    return f"{DOCPROOF_URL}/j_spring_security_check"


def get_json(client: Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch JSON from DocProof using bounded network timeouts."""
    response = client.get(f"{DOCPROOF_URL}{path}", params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def normalize_document_number(raw_document_number: str) -> str:
    """Normalize the document number using the existing first-segment rule."""
    return raw_document_number.split("/")[0].strip()


def find_latest_edms_object_id(entries: list[dict[str, Any]]) -> str | None:
    """Return the newest EDMS proof-reading object id from search entries."""
    latest_entry = None
    for entry in entries:
        properties = entry.get("content", {}).get("properties", {})
        if properties.get("pr_status") != "EDMS":
            continue
        if latest_entry is None or properties.get("pr_no", 0) > latest_entry.get("pr_no", 0):
            latest_entry = properties
    return None if latest_entry is None else latest_entry.get("id")


def find_document_issue(entries: list[dict[str, Any]]) -> int:
    """Return the first supported technical document issue number."""
    supported_types = {"dprf_technical_document", "dprf_cdcp_document"}
    for entry in entries:
        content = entry.get("content", {})
        if content.get("type") in supported_types:
            return content.get("properties", {}).get("issue", 0)
    return 0


def search_issue_number(document_number: str, client: Session = session) -> tuple[int | None, str | None]:
    """Return the published DocProof issue number and optional failure reason."""
    search_result = get_json(client, "/realtime-queries/dprf_search_proof_readin", search_params(document_number))
    if search_result.get("total", 0) <= 0:
        return None, "missing"
    object_id = find_latest_edms_object_id(search_result.get("entries", []))
    if not object_id:
        return None, "unpublished"
    document_object = get_json(client, f"/folders/dprf_proof_reading/{object_id}/objects", {"inline": "true"})
    return find_document_issue(document_object.get("entries", [])), None


def search_params(document_number: str) -> dict[str, str]:
    """Return encoded DocProof search query parameters."""
    return {"inline": "true", "input_document_number": document_number}


@api_view(["GET"])
@permission_classes([AllowAny])
def test(request):
    """Return a lightweight DocProof route health response."""
    return Response("DOCPROOF SUCCESS")


@api_view(["GET"])
@permission_classes([AllowAny])
def search(request):
    """Search DocProof and return the published issue number for a document."""
    document_number = request.query_params.get("document_no")
    if not document_number:
        return Response({"detail": "Document number required."}, status=400)
    return search_response(normalize_document_number(document_number))


def search_response(document_number: str) -> Response:
    """Build the existing DocProof search API response."""
    try:
        issue_number, failure_reason = search_issue_number(document_number)
    except HTTPError:
        LOGGER.info("Retrying DocProof search after refreshing session.")
        login()
        issue_number, failure_reason = search_issue_number(document_number)
    except RequestException as exception:
        LOGGER.warning("DocProof request failed: %s", exception)
        return Response(f"Something went wrong: {exception}", status=400)
    if issue_number is None:
        message = missing_document_message(document_number, failure_reason)
        return Response({"message": message}, status=400)
    return Response(issue_number, status=200)


def missing_document_message(document_number: str, failure_reason: str | None) -> str:
    """Return the legacy user-facing missing document message."""
    if failure_reason == "unpublished":
        return f"Can not find published document in EDMS: {document_number}"
    return f"Can not find or access document: {document_number}"
