"""Fail-closed mTLS identity extraction for the outbound Windows bridge."""

import hashlib
import hmac
import ipaddress
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import unquote

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from django.conf import settings
from rest_framework.exceptions import APIException

FINGERPRINT_PATTERN = re.compile(r"^[A-F0-9]{64}$")
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


class BridgeAuthenticationFailed(APIException):
    """Reject every non-mTLS or ambiguously proxied bridge request."""

    status_code = 403
    default_code = "BRIDGE_AUTHENTICATION_FAILED"
    default_detail = "Windows bridge authentication failed."


@dataclass(frozen=True)
class AgentIdentity:
    """Represent one certificate-bound bridge agent without exposing its DN."""

    worker_id: str


def bridge_configuration_ready() -> bool:
    """Return whether trusted proxy and client-certificate policy is complete."""

    raw_fingerprints = setting_list("WINDOWS_BRIDGE_CLIENT_FINGERPRINTS")
    fingerprints = trusted_fingerprints()
    raw_subjects = setting_subjects()
    subjects = trusted_subjects()
    raw_proxy_addresses = setting_list("WINDOWS_BRIDGE_TRUSTED_PROXY_IPS")
    proxy_addresses = trusted_proxy_addresses()
    return bool(
        setting_bool("WINDOWS_BRIDGE_ENABLED")
        and setting_bool("WINDOWS_BRIDGE_TRUST_PROXY_HEADERS")
        and fingerprints
        and proxy_addresses
        and len(fingerprints) == len(raw_fingerprints)
        and len(proxy_addresses) == len(raw_proxy_addresses)
        and (not raw_subjects or len(subjects) == len(raw_subjects))
    )


def authenticate_agent(request) -> AgentIdentity:
    """Authenticate a certificate asserted only by one explicitly trusted proxy."""

    if not bridge_configuration_ready() or not request.is_secure():
        raise BridgeAuthenticationFailed()
    if request.META.get("HTTP_AUTHORIZATION") or request.META.get("HTTP_COOKIE"):
        raise BridgeAuthenticationFailed()
    try:
        remote_address = str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError as error:
        raise BridgeAuthenticationFailed() from error
    if remote_address not in trusted_proxy_addresses():
        raise BridgeAuthenticationFailed()
    if request.META.get("HTTP_X_AWC_MTLS_VERIFIED") != "SUCCESS":
        raise BridgeAuthenticationFailed()

    certificate = parse_forwarded_certificate(
        request.META.get("HTTP_X_AWC_MTLS_CERT", "")
    )
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex().upper()
    if not fingerprint or not any(
        hmac.compare_digest(fingerprint, allowed)
        for allowed in trusted_fingerprints()
    ):
        raise BridgeAuthenticationFailed()

    subject = certificate.subject.rfc4514_string()
    if not subject or len(subject) > 512 or CONTROL_CHARACTER_PATTERN.search(subject):
        raise BridgeAuthenticationFailed()
    allowed_subjects = trusted_subjects()
    if allowed_subjects and not any(
        hmac.compare_digest(subject, allowed) for allowed in allowed_subjects
    ):
        raise BridgeAuthenticationFailed()

    opaque_id = hashlib.sha256(fingerprint.encode("ascii")).hexdigest()[:32]
    return AgentIdentity(worker_id=f"windows:{opaque_id}")


def parse_forwarded_certificate(value):
    """Parse one bounded Nginx escaped PEM certificate and enforce its validity window."""

    encoded = str(value or "")
    if not encoded or len(encoded) > 16384:
        raise BridgeAuthenticationFailed()
    try:
        decoded = unquote(encoded, errors="strict")
        envelope = decoded.strip()
        if (
            envelope.count("-----BEGIN CERTIFICATE-----") != 1
            or envelope.count("-----END CERTIFICATE-----") != 1
            or not envelope.startswith("-----BEGIN CERTIFICATE-----")
            or not envelope.endswith("-----END CERTIFICATE-----")
        ):
            raise ValueError("Unexpected certificate envelope.")
        certificate = x509.load_pem_x509_certificate(envelope.encode("ascii"))
    except (ValueError, UnicodeError) as error:
        raise BridgeAuthenticationFailed() from error
    now = datetime.now(timezone.utc)
    if certificate.not_valid_before_utc > now or certificate.not_valid_after_utc < now:
        raise BridgeAuthenticationFailed()
    return certificate


def trusted_fingerprints() -> tuple[str, ...]:
    """Return normalized SHA-256 certificate fingerprints, rejecting malformed entries."""

    values = setting_list("WINDOWS_BRIDGE_CLIENT_FINGERPRINTS")
    normalized = tuple(normalize_fingerprint(value) for value in values)
    return tuple(value for value in normalized if value)


def trusted_subjects() -> tuple[str, ...]:
    """Return optional exact-match certificate subjects."""

    return tuple(
        value
        for value in setting_subjects()
        if value and len(value) <= 512 and not CONTROL_CHARACTER_PATTERN.search(value)
    )


def trusted_proxy_addresses() -> frozenset[str]:
    """Return canonical IP addresses allowed to assert mTLS headers."""

    addresses = set()
    for value in setting_list("WINDOWS_BRIDGE_TRUSTED_PROXY_IPS"):
        try:
            addresses.add(str(ipaddress.ip_address(value)))
        except ValueError:
            continue
    return frozenset(addresses)


def normalize_fingerprint(value) -> str:
    """Normalize a colon-delimited SHA-256 fingerprint or reject it."""

    normalized = str(value or "").replace(":", "").strip().upper()
    return normalized if FINGERPRINT_PATTERN.fullmatch(normalized) else ""


def setting_bool(name: str) -> bool:
    """Read a bridge-local boolean while remaining compatible with root settings."""

    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(name, "")
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def setting_list(name: str) -> tuple[str, ...]:
    """Read a bridge-local comma-separated allowlist without adding global state."""

    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(name, "")
    if isinstance(value, str):
        values = value.split(",")
    else:
        values = value or ()
    return tuple(str(item).strip() for item in values if str(item).strip())


def setting_subjects() -> tuple[str, ...]:
    """Read exact certificate subjects without splitting commas inside a DN."""

    value = getattr(settings, "WINDOWS_BRIDGE_CLIENT_SUBJECTS", None)
    if value is None:
        value = os.environ.get("WINDOWS_BRIDGE_CLIENT_SUBJECTS", "")
    values = value.split("||") if isinstance(value, str) else value or ()
    return tuple(str(item).strip() for item in values if str(item).strip())
