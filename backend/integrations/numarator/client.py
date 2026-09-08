"""Bounded client for Numarator's private v1 API."""

import hashlib
import json
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from requests.exceptions import RequestException

from awcenter.outbound_urls import normalize_outbound_base_url

FORMAT_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class NumaratorError(Exception):
    """Base safe integration failure."""


class NumaratorConfigurationError(NumaratorError):
    """The server-side integration configuration is incomplete or unsafe."""


class NumaratorTemporaryError(NumaratorError):
    """The request can be retried with the same idempotency contract."""


class NumaratorRejectedError(NumaratorError):
    """Numarator rejected a well-formed request."""


class NumaratorConflictError(NumaratorError):
    """The remote state must be reconciled before continuing."""


@dataclass(frozen=True)
class GeneratedNumber:
    remote_id: int
    number: str
    format_code: str
    status: str
    request_id: str


def credential_fingerprint() -> str:
    """Identify the configured credential version without persisting its secret."""

    credential_id = str(settings.NUMARATOR_CREDENTIAL_ID or "").strip()
    return (
        hashlib.sha256(credential_id.encode("utf-8")).hexdigest()[:16]
        if credential_id
        else ""
    )


def project_format_code(project_slug: str) -> str:
    """Return the legacy default only when a project has one allowed format."""

    codes = project_format_codes(project_slug)
    return codes[0] if len(codes) == 1 else ""


def project_format_codes(project_slug: str) -> list[str]:
    """Read the server-owned allowlist, accepting legacy single-code mappings."""

    mappings = settings.NUMARATOR_PROJECT_FORMATS
    if not isinstance(mappings, dict):
        return []
    values = mappings.get(project_slug, [])
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(
        value.strip() for value in values
        if isinstance(value, str) and FORMAT_CODE_PATTERN.fullmatch(value.strip())
    ))


def is_configured(project_slug: str, *, require_credential: bool = False) -> bool:
    """Report whether the requested integration surface has required settings."""

    configured = bool(
        settings.NUMARATOR_ENABLED
        and settings.NUMARATOR_BASE_URL
        and settings.NUMARATOR_CREDENTIAL_ID
        and project_format_codes(project_slug)
    )
    return configured and (bool(settings.NUMARATOR_API_KEY) or not require_credential)


class NumaratorClient:
    """Call the allowlisted Numarator endpoints with bounded JSON responses."""

    def __init__(self, session=None):
        if not settings.NUMARATOR_ENABLED or not settings.NUMARATOR_API_KEY:
            raise NumaratorConfigurationError("Numarator is not configured.")
        try:
            self.base_url = normalize_outbound_base_url(
                settings.NUMARATOR_BASE_URL,
                require_https=not settings.DEBUG,
            )
        except ValueError as error:
            raise NumaratorConfigurationError("Numarator URL is invalid.") from error
        self.session = session or requests.Session()
        self.session.verify = settings.NUMARATOR_VERIFY_SSL
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": settings.NUMARATOR_API_KEY,
            }
        )

    def close(self):
        """Release the request-local HTTP session."""

        self.session.close()

    def generate_number(
        self,
        *,
        format_code: str,
        context_data: dict,
        metadata: dict,
        external_reference: str,
        idempotency_key: str,
    ) -> GeneratedNumber:
        payload = self._request(
            "POST",
            "/api/private/v1/numbers/",
            body={
                "format_code": format_code,
                "context_data": context_data,
                "metadata": metadata,
                "external_reference": external_reference,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        data = _response_data(payload)
        try:
            remote_id = int(data["id"])
            number = str(data["document_number"])
            response_format = str(data["format_code"])
            remote_status = str(data["status"])
        except (KeyError, TypeError, ValueError) as error:
            raise NumaratorConflictError("Numarator returned an incomplete result.") from error
        if remote_id <= 0 or not number or remote_status not in {"active", "used"}:
            raise NumaratorConflictError("Numarator returned an unexpected result.")
        return GeneratedNumber(
            remote_id=remote_id,
            number=number,
            format_code=response_format,
            status=remote_status,
            request_id=str(payload.get("_request_id", ""))[:128],
        )

    def mark_used(self, remote_id: int) -> GeneratedNumber:
        payload = self._request(
            "PATCH",
            f"/api/private/v1/numbers/{int(remote_id)}/status/",
            body={"status": "used"},
        )
        data = _response_data(payload)
        try:
            return GeneratedNumber(
                remote_id=int(data["id"]),
                number=str(data["document_number"]),
                format_code=str(data["format_code"]),
                status=str(data["status"]),
                request_id=str(payload.get("_request_id", ""))[:128],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NumaratorConflictError("Numarator returned an incomplete result.") from error

    def _request(self, method: str, path: str, *, body: dict, headers=None) -> dict:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                json=body,
                headers=headers or {},
                timeout=(
                    settings.NUMARATOR_CONNECT_TIMEOUT_SECONDS,
                    settings.NUMARATOR_READ_TIMEOUT_SECONDS,
                ),
                stream=True,
                allow_redirects=False,
            )
        except RequestException as error:
            raise NumaratorTemporaryError("Numarator is temporarily unavailable.") from error
        try:
            if response.status_code == 409:
                raise NumaratorConflictError("Numarator reported a state conflict.")
            if response.status_code == 429 or response.status_code >= 500:
                raise NumaratorTemporaryError("Numarator is temporarily unavailable.")
            if response.status_code < 200 or response.status_code >= 300:
                raise NumaratorRejectedError("Numarator rejected the request.")
            payload = json.loads(_read_bounded(response).decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise NumaratorConflictError("Numarator returned an invalid result.")
            payload["_request_id"] = response.headers.get("X-Request-ID", "")
            return payload
        except (UnicodeError, json.JSONDecodeError) as error:
            raise NumaratorConflictError("Numarator returned an invalid result.") from error
        finally:
            response.close()


def _response_data(payload: dict) -> dict:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise NumaratorConflictError("Numarator returned an invalid result.")
    return data


def _read_bounded(response) -> bytes:
    maximum = max(1, int(settings.NUMARATOR_MAX_RESPONSE_BYTES))
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > maximum:
                raise NumaratorConflictError("Numarator response exceeded the safety limit.")
        except ValueError as error:
            raise NumaratorConflictError("Numarator returned an invalid result.") from error
    content = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > maximum:
            raise NumaratorConflictError("Numarator response exceeded the safety limit.")
    return bytes(content)
