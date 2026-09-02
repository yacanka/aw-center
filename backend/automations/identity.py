"""Fail-closed identity for the host-local DOORS runner."""

import hashlib
import hmac
import re
from dataclasses import dataclass

from django.conf import settings
from rest_framework.exceptions import APIException

RUNNER_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


class RunnerAuthenticationFailed(APIException):
    """Reject requests that do not carry the configured runner credential."""

    status_code = 403
    default_code = "DOORS_RUNNER_AUTHENTICATION_FAILED"
    default_detail = "DOORS runner authentication failed."


@dataclass(frozen=True)
class RunnerIdentity:
    """Represent one token-bound runner without exposing its credential."""

    worker_id: str


def runner_configuration_ready() -> bool:
    """Return whether the local runner credential satisfies the security policy."""

    return bool(settings.DOORS_ENABLED and valid_runner_token(configured_runner_token()))


def authenticate_runner(request) -> RunnerIdentity:
    """Authenticate the host-local runner with its dedicated shared secret."""

    if not runner_configuration_ready():
        raise RunnerAuthenticationFailed()
    if request.META.get("HTTP_AUTHORIZATION") or request.META.get("HTTP_COOKIE"):
        raise RunnerAuthenticationFailed()

    configured = configured_runner_token()
    presented = str(request.META.get("HTTP_X_AWC_RUNNER_TOKEN", ""))
    if not valid_runner_token(presented) or not hmac.compare_digest(presented, configured):
        raise RunnerAuthenticationFailed()

    opaque_id = hashlib.sha256(configured.encode("ascii")).hexdigest()[:32]
    return RunnerIdentity(worker_id=f"doors:{opaque_id}")


def configured_runner_token() -> str:
    """Read the deployment-provided token without applying lossy normalization."""

    return str(getattr(settings, "DOORS_RUNNER_TOKEN", ""))


def valid_runner_token(value: str) -> bool:
    """Require at least 256 bits of URL-safe generated credential material."""

    return bool(RUNNER_TOKEN_PATTERN.fullmatch(str(value or "")))
