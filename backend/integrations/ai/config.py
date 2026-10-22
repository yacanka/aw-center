"""Fail-closed provider validation; settings resolution belongs only here."""

import math
from dataclasses import replace
from typing import Literal
from urllib.parse import urlsplit

from django.conf import settings

from .contracts import AIConfiguration, AIServiceError

_DEFAULTS = {
    "URL": "",
    "MODEL_ID": "",
    "TOKEN": "",
    "ALLOWED_HOSTS": (),
    "CONNECT_TIMEOUT_SECONDS": 5.0,
    "READ_TIMEOUT_SECONDS": 60.0,
    "MAX_RESPONSE_BYTES": 1024 * 1024,
}


def configuration_error() -> AIServiceError:
    return AIServiceError(
        "The AI service is not configured safely.", "AI_CONFIGURATION_ERROR", 503,
    )


def resolve_configuration() -> AIConfiguration:
    """Validate the sole AI_API provider without network access or fallbacks."""
    values = {
        suffix: getattr(settings, f"AI_API_{suffix}", None)
        for suffix in _DEFAULTS
    }
    values = {suffix: _DEFAULTS[suffix] if value is None else value
              for suffix, value in values.items()}
    try:
        hosts = values["ALLOWED_HOSTS"]
        if isinstance(hosts, str):
            hosts = tuple(host.strip() for host in hosts.split(","))
        elif isinstance(hosts, (list, tuple)):
            hosts = tuple(hosts)
        else:
            raise ValueError("Invalid allowlist")
        maximum = values["MAX_RESPONSE_BYTES"]
        if isinstance(maximum, str):
            maximum = int(maximum)
        return validate_configuration(AIConfiguration(
            url=values["URL"], model=values["MODEL_ID"], token=values["TOKEN"],
            allowed_hosts=hosts,
            connect_timeout=values["CONNECT_TIMEOUT_SECONDS"],
            read_timeout=values["READ_TIMEOUT_SECONDS"],
            max_response_bytes=maximum,
        ))
    except (TypeError, ValueError, OverflowError):
        raise configuration_error() from None


def configuration_status() -> Literal["configured", "unconfigured", "invalid"]:
    """Return safe configuration readiness; never probe or disclose provider data."""
    if all(getattr(settings, f"AI_API_{suffix}", None) is None for suffix in _DEFAULTS):
        return "unconfigured"
    try:
        resolve_configuration()
    except AIServiceError:
        return "invalid"
    return "configured"


def validate_configuration(configuration: AIConfiguration) -> AIConfiguration:
    """Reject unsafe endpoints and limits before opening a network connection."""
    if not isinstance(configuration, AIConfiguration):
        raise configuration_error()
    try:
        url = validated_url(configuration.url, configuration.allowed_hosts)
        model = validated_text(configuration.model)
        token = validated_text(configuration.token)
        token.encode("ascii")  # Bearer credentials must be safe HTTP header text.
        connect = validated_timeout(configuration.connect_timeout, 60)
        read = validated_timeout(configuration.read_timeout, 300)
        maximum = configuration.max_response_bytes
        if type(maximum) is not int or not 1024 <= maximum <= 10 * 1024 * 1024:
            raise ValueError("Invalid response limit")
    except (TypeError, ValueError, OverflowError):
        raise configuration_error() from None
    return replace(configuration, url=url, model=model, token=token,
                   connect_timeout=connect, read_timeout=read)


def validated_text(value: str) -> str:
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid configuration text")
    value = value.strip()
    if not value:
        raise ValueError("Missing configuration text")
    value.encode("utf-8")
    return value


def validated_timeout(value: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError("Invalid timeout")
    timeout = float(value)
    if not math.isfinite(timeout) or not 0 < timeout <= maximum:
        raise ValueError("Invalid timeout")
    return timeout


def validated_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    url = validated_text(url)
    if not isinstance(allowed_hosts, tuple) or not allowed_hosts:
        raise ValueError("Missing allowlist")
    hosts = {validated_text(host).lower() for host in allowed_hosts}
    if any(any(char in host for char in "/*?#@\\") for host in hosts):
        raise ValueError("Invalid allowlist")
    parsed = urlsplit(url)
    port = parsed.port  # Force validation: urlsplit otherwise accepts malformed ports.
    if (parsed.scheme.lower() != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or "\\" in url
            or parsed.hostname.lower() not in hosts or port == 0):
        raise ValueError("Unsafe URL")
    return url
