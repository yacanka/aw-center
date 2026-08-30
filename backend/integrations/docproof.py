"""Bounded DocProof adapter and response parsing."""

import logging
import json
from typing import Any

import requests
from django.conf import settings
from requests import Session
from requests.exceptions import RequestException

from awcenter.outbound_urls import normalize_outbound_base_url

LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 10
LOGIN_TIMEOUT_SECONDS = 5


def get_credentials() -> tuple[str, str] | None:
    """Return process-environment credentials without reversible source encoding."""

    if not settings.DOCPROOF_USERNAME or not settings.DOCPROOF_PASSWORD:
        return None
    return settings.DOCPROOF_USERNAME, settings.DOCPROOF_PASSWORD


def login(client: Session) -> bool:
    """Authenticate one request-local DocProof session without logging secrets."""

    credentials = get_credentials()
    if not credentials:
        LOGGER.warning("DocProof credentials are not configured.")
        return False
    payload = {"j_username": credentials[0], "j_password": credentials[1]}
    try:
        response = client.post(
            login_url(),
            data=payload,
            timeout=LOGIN_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        response.raise_for_status()
    except RequestException as error:
        LOGGER.warning("DocProof login failed: %s", type(error).__name__)
        return False
    finally:
        if "response" in locals():
            response.close()
    return True


def login_url() -> str:
    """Return the DocProof login endpoint URL."""

    return f"{base_url()}/j_spring_security_check"


def get_json(client: Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch one bounded JSON object with TLS verification enabled by policy."""

    response = client.get(
        f"{base_url()}{path}",
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
        stream=True,
        allow_redirects=False,
    )
    try:
        response.raise_for_status()
        payload = json.loads(read_bounded_response(response).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RequestException("DocProof returned an invalid response.") from error
    finally:
        response.close()
    return payload if isinstance(payload, dict) else {}


def search_document_issue(document_number: str) -> tuple[int | None, str | None]:
    """Authenticate and search inside one isolated HTTP session."""

    if not settings.DOCPROOF_ENABLED:
        raise RequestException("DocProof is disabled.")
    with requests.Session() as client:
        client.verify = tls_verification()
        if not login(client):
            raise RequestException("DocProof authentication failed.")
        return search_issue_number(document_number, client)


def read_bounded_response(response) -> bytes:
    """Read a streamed response without trusting Content-Length."""

    maximum = max(1, int(settings.DOCPROOF_MAX_RESPONSE_BYTES))
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > maximum:
                raise RequestException("DocProof response exceeded the safety limit.")
        except ValueError as error:
            raise RequestException("DocProof returned an invalid response.") from error
    content = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > maximum:
            raise RequestException("DocProof response exceeded the safety limit.")
    return bytes(content)


def base_url() -> str:
    try:
        return normalize_outbound_base_url(
            settings.DOCPROOF_URL,
            require_https=not settings.DEBUG,
        )
    except ValueError as error:
        raise RequestException("DocProof URL configuration is invalid.") from error


def tls_verification() -> bool | str:
    certificate = settings.DOCPROOF_CERTIFICATE_FILE
    return str(certificate) if certificate.exists() else settings.DOCPROOF_VERIFY_SSL


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
    client: Session,
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
