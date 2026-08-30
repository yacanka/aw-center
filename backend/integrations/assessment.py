"""Fail-closed adapter for the configured document assessment service."""

from urllib.parse import urlsplit

import requests
from django.conf import settings

DEFAULT_HEADERS = {
    "Accept": "text/plain",
    "Content-Type": "application/json; charset=utf-8",
}


class AssessmentServiceError(RuntimeError):
    """Represent a sanitized assessment configuration or upstream failure."""

    def __init__(self, detail, code, response_status):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.response_status = response_status


def request_assessment(payload):
    """Return bounded decoded response lines from the allowlisted HTTPS service."""

    url = validated_assessment_url()
    timeout = validated_timeout()
    maximum_bytes = validated_maximum_response_bytes()
    try:
        with requests.post(
            url,
            json=payload,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise AssessmentServiceError(
                    "The assessment service rejected the request.",
                    "ASSESSMENT_UPSTREAM_REJECTED",
                    502,
                )
            return read_bounded_lines(response, maximum_bytes)
    except requests.RequestException as error:
        raise AssessmentServiceError(
            "The assessment service is unavailable.",
            "ASSESSMENT_UNAVAILABLE",
            503,
        ) from error


def validated_assessment_url():
    """Return an HTTPS URL whose hostname is explicitly allowlisted."""

    url = str(settings.ASSESSMENT_API_URL or "").strip()
    parsed = urlsplit(url)
    configured_hosts = settings.ASSESSMENT_API_ALLOWED_HOSTS
    if isinstance(configured_hosts, str):
        configured_hosts = configured_hosts.split(",")
    allowed_hosts = {
        str(host).strip().lower()
        for host in configured_hosts
        if str(host).strip()
    }
    if (
        not url
        or parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.hostname.lower() not in allowed_hosts
    ):
        raise AssessmentServiceError(
            "The assessment service is not configured safely.",
            "ASSESSMENT_CONFIGURATION_ERROR",
            503,
        )
    return url


def validated_timeout():
    """Return positive bounded connect and read timeouts."""

    connect = float(settings.ASSESSMENT_API_CONNECT_TIMEOUT_SECONDS)
    read = float(settings.ASSESSMENT_API_READ_TIMEOUT_SECONDS)
    if not 0 < connect <= 60 or not 0 < read <= 300:
        raise AssessmentServiceError(
            "The assessment service is not configured safely.",
            "ASSESSMENT_CONFIGURATION_ERROR",
            503,
        )
    return connect, read


def validated_maximum_response_bytes():
    """Return a bounded response limit suitable for streamed text."""

    maximum = int(settings.ASSESSMENT_API_MAX_RESPONSE_BYTES)
    if not 1024 <= maximum <= 10 * 1024 * 1024:
        raise AssessmentServiceError(
            "The assessment service is not configured safely.",
            "ASSESSMENT_CONFIGURATION_ERROR",
            503,
        )
    return maximum


def read_bounded_lines(response, maximum_bytes):
    """Decode non-empty response lines without buffering an unbounded body."""

    body = bytearray()
    received = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        received += len(chunk)
        if received > maximum_bytes:
            raise AssessmentServiceError(
                "The assessment service returned an invalid response.",
                "ASSESSMENT_RESPONSE_INVALID",
                502,
            )
        body.extend(chunk)
    return [
        raw_line.decode("utf-8", errors="replace")
        for raw_line in bytes(body).splitlines()
        if raw_line
    ]
