from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

from django.conf import settings

from .client import TeamcenterClient
from .config import AuthMode, TeamcenterClientConfig
from .exceptions import TeamcenterConfigurationError

Result = TypeVar("Result")


def parse_tls_verification(raw_value: str) -> bool | str:
    """Parse a boolean or CA-bundle Teamcenter TLS setting."""
    normalized = raw_value.strip()
    if normalized.lower() in {"true", "1", "yes", "on"}:
        return True
    if normalized.lower() in {"false", "0", "no", "off"}:
        return False
    return str(Path(normalized))


def validate_transport_security(base_url: str, verify_ssl: bool | str) -> None:
    """Reject insecure Teamcenter transport outside development."""
    if settings.DEBUG:
        return
    if urlsplit(base_url).scheme != "https":
        raise TeamcenterConfigurationError("Production Teamcenter URLs must use HTTPS.")
    if verify_ssl is False:
        raise TeamcenterConfigurationError("TLS verification cannot be disabled in production.")


def build_client_config() -> TeamcenterClientConfig:
    """Build Teamcenter client configuration from Django settings."""
    verify_ssl = parse_tls_verification(settings.TEAMCENTER_VERIFY_SSL)
    validate_transport_security(settings.TEAMCENTER_BASE_URL, verify_ssl)
    try:
        auth_mode = AuthMode(settings.TEAMCENTER_AUTH_MODE.lower())
    except ValueError as error:
        raise TeamcenterConfigurationError("Invalid TEAMCENTER_AUTH_MODE.") from error
    return TeamcenterClientConfig(**client_config_values(auth_mode, verify_ssl))


def client_config_values(auth_mode: AuthMode, verify_ssl: bool | str) -> dict[str, Any]:
    """Return Teamcenter client constructor values from settings."""
    return {
        "base_url": settings.TEAMCENTER_BASE_URL,
        "service_root": settings.TEAMCENTER_SERVICE_ROOT,
        "auth_mode": auth_mode,
        "username": settings.TEAMCENTER_USERNAME,
        "password": settings.TEAMCENTER_PASSWORD,
        "group": settings.TEAMCENTER_GROUP,
        "role": settings.TEAMCENTER_ROLE,
        "verify_ssl": verify_ssl,
        "jsessionid": settings.TEAMCENTER_JSESSIONID,
        "csrf_token": settings.TEAMCENTER_XSRF_TOKEN,
        "connect_timeout_seconds": settings.TEAMCENTER_CONNECT_TIMEOUT_SECONDS,
        "read_timeout_seconds": settings.TEAMCENTER_READ_TIMEOUT_SECONDS,
        "max_read_retries": settings.TEAMCENTER_MAX_READ_RETRIES,
        "max_response_bytes": settings.TEAMCENTER_MAX_RESPONSE_BYTES,
    }


def execute_with_client(operation: Callable[[TeamcenterClient], Result]) -> Result:
    """Execute an operation in an isolated Teamcenter session."""
    with TeamcenterClient(build_client_config()) as client:
        return operation(client)


def integration_status() -> dict[str, Any]:
    """Return non-secret Teamcenter integration configuration status."""
    auth_mode = settings.TEAMCENTER_AUTH_MODE.lower()
    try:
        build_client_config()
        configured = True
    except TeamcenterConfigurationError:
        configured = False
    return {
        "configured": configured,
        "auth_mode": auth_mode,
        "service_root": settings.TEAMCENTER_SERVICE_ROOT,
        "tls_verification_enabled": parse_tls_verification(settings.TEAMCENTER_VERIFY_SSL) is not False,
    }
