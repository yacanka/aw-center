"""Bounded DocProof HTTP client and response parsing."""

import logging
from base64 import b64decode
from binascii import Error as Base64DecodeError
from typing import Any

import requests
from django.conf import settings
from requests import Session
from requests.exceptions import RequestException

LOGGER = logging.getLogger(__name__)
CERTIFICATE_FILE = settings.DOCPROOF_CERTIFICATE_FILE
DOCPROOF_URL = settings.DOCPROOF_URL.rstrip("/")
REQUEST_TIMEOUT_SECONDS = 10
LOGIN_TIMEOUT_SECONDS = 5

session = requests.Session()
session.verify = str(CERTIFICATE_FILE) if CERTIFICATE_FILE.exists() else settings.DOCPROOF_VERIFY_SSL


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
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def normalize_document_number(raw_document_number: str) -> str:
    """Normalize the document number using the existing first-segment rule."""

    return raw_document_number.split("/")[0].strip()


def find_latest_edms_object_id(entries: list[dict[str, Any]]) -> str | None:
    """Return the newest EDMS proof-reading object id from search entries."""

    published = (_properties(entry) for entry in entries)
    published = [item for item in published if item.get("pr_status") == "EDMS"]
    latest = max(published, key=lambda item: _safe_number(item.get("pr_no")), default=None)
    return str(latest.get("id")) if latest and latest.get("id") is not None else None


def find_document_issue(entries: list[dict[str, Any]]) -> int:
    """Return the first supported technical document issue number."""

    supported_types = {"dprf_technical_document", "dprf_cdcp_document"}
    for entry in entries:
        content = entry.get("content", {})
        if isinstance(content, dict) and content.get("type") in supported_types:
            return _safe_number(_properties(entry).get("issue"))
    return 0


def search_issue_number(
    document_number: str,
    client: Session = session,
) -> tuple[int | None, str | None]:
    """Return the published DocProof issue number and optional failure reason."""

    search_result = get_json(
        client,
        "/realtime-queries/dprf_search_proof_readin",
        search_params(document_number),
    )
    entries = search_result.get("entries", [])
    if _safe_number(search_result.get("total")) <= 0 or not isinstance(entries, list):
        return None, "missing"
    object_id = find_latest_edms_object_id(entries)
    if not object_id:
        return None, "unpublished"
    result = get_json(client, f"/folders/dprf_proof_reading/{object_id}/objects", {"inline": "true"})
    objects = result.get("entries", [])
    return find_document_issue(objects if isinstance(objects, list) else []), None


def search_params(document_number: str) -> dict[str, str]:
    """Return encoded DocProof search query parameters."""

    return {"inline": "true", "input_document_number": document_number}


def _properties(entry):
    content = entry.get("content", {}) if isinstance(entry, dict) else {}
    properties = content.get("properties", {}) if isinstance(content, dict) else {}
    return properties if isinstance(properties, dict) else {}


def _safe_number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
