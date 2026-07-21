"""Sanitized live-health adapters for Integration Hub bridges."""

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from django.conf import settings
import requests

from doors.services import integration_status as doors_status
from teamcenter.services import parse_tls_verification


@dataclass(frozen=True)
class ProbeOutcome:
    """Represent a non-secret integration health observation."""

    status: str
    detail: str


def probe_integration(identifier: str) -> ProbeOutcome:
    """Run the adapter registered for an integration identifier."""

    adapter = PROBE_ADAPTERS.get(identifier)
    if adapter is None:
        return ProbeOutcome("unsupported", "No live probe adapter is available.")
    return adapter()


def probe_jira() -> ProbeOutcome:
    """Check whether the configured JIRA origin accepts a connection."""

    return _http_probe(settings.JIRA_URL, True)


def probe_teamcenter() -> ProbeOutcome:
    """Check Teamcenter reachability without authenticating or exposing secrets."""

    verify_ssl = parse_tls_verification(settings.TEAMCENTER_VERIFY_SSL)
    return _http_probe(settings.TEAMCENTER_BASE_URL, verify_ssl)


def probe_docproof() -> ProbeOutcome:
    """Check DocProof reachability without sending configured credentials."""

    if not settings.AW_USERNAME or not settings.AW_PASSWORD:
        return ProbeOutcome("not_configured", "Server credentials are not configured.")
    return _http_probe(settings.DOCPROOF_URL, True)


def probe_doors() -> ProbeOutcome:
    """Check local DOORS platform and executable availability without opening COM."""

    status = doors_status()
    if not status["configured"]:
        return ProbeOutcome("not_configured", "The client executable is not configured.")
    if not status["platform_supported"]:
        return ProbeOutcome("unsupported", "The local runtime does not support DOORS OLE.")
    if _executable_exists(settings.DOORS_EXECUTABLE):
        return ProbeOutcome("available", "The local client executable is available.")
    return ProbeOutcome("unavailable", "The configured local client executable was not found.")


def probe_office() -> ProbeOutcome:
    """Check Python parsers and optional presentation conversion binaries."""

    packages = ("openpyxl", "docx", "pypdf", "extract_msg")
    if not all(importlib.util.find_spec(package) for package in packages):
        return ProbeOutcome("unavailable", "One or more document parser packages are missing.")
    binaries = (settings.SOFFICE_BIN, settings.PDFTOPPM_BIN)
    if not all(_executable_exists(binary) for binary in binaries):
        return ProbeOutcome("degraded", "Core parsers are ready; presentation preview tools are missing.")
    return ProbeOutcome("available", "Document parsers and presentation tools are available.")


def probe_media() -> ProbeOutcome:
    """Check local FFmpeg availability without spawning a process."""

    if _executable_exists(settings.FFMPEG_EXECUTABLE):
        return ProbeOutcome("available", "The configured media converter is available.")
    return ProbeOutcome("unavailable", "The configured media converter was not found.")


def probe_ai() -> ProbeOutcome:
    """Check local AI packages and model directories without loading them."""

    runtimes = ("transformers", "sentence_transformers")
    if not all(importlib.util.find_spec(runtime) for runtime in runtimes):
        return ProbeOutcome("unavailable", "One or more local AI runtimes are missing.")
    models = (
        settings.WORD_TRANSLATION_TR_EN_MODEL,
        settings.WORD_TRANSLATION_EN_TR_MODEL,
        settings.WORD_ANALYZER_BI_MODEL,
        settings.WORD_ANALYZER_CROSS_MODEL,
    )
    if not all(Path(model).is_dir() for model in models):
        return ProbeOutcome("not_configured", "One or more local AI models are missing.")
    return ProbeOutcome("available", "Local AI runtimes and model directories are available.")


def _http_probe(url: str, verify_ssl: bool | str) -> ProbeOutcome:
    if not url:
        return ProbeOutcome("not_configured", "The service endpoint is not configured.")
    if not _transport_is_allowed(url, verify_ssl):
        return ProbeOutcome("degraded", "The endpoint does not satisfy secure transport policy.")
    try:
        response = requests.head(
            url,
            allow_redirects=False,
            headers={"User-Agent": "AW-Center-Integration-Probe"},
            stream=True,
            timeout=_probe_timeout(),
            verify=verify_ssl,
        )
        response.close()
        if response.status_code < 500:
            return ProbeOutcome("available", "The service endpoint is reachable.")
        return ProbeOutcome("degraded", "The service endpoint returned a server error.")
    except (OSError, requests.RequestException):
        return ProbeOutcome("unavailable", "The service endpoint could not be reached.")


def _transport_is_allowed(url: str, verify_ssl: bool | str) -> bool:
    parsed_url = urlsplit(url)
    scheme = parsed_url.scheme.lower()
    if scheme not in {"http", "https"}:
        return False
    if parsed_url.username or parsed_url.password or not parsed_url.hostname:
        return False
    if settings.DEBUG:
        return True
    return scheme == "https" and verify_ssl is not False


def _probe_timeout() -> tuple[float, float]:
    return (
        _bounded(settings.INTEGRATION_PROBE_CONNECT_TIMEOUT_SECONDS, 0.1, 10.0),
        _bounded(settings.INTEGRATION_PROBE_READ_TIMEOUT_SECONDS, 0.1, 15.0),
    )


def _executable_exists(executable: str) -> bool:
    return bool(shutil.which(executable) or Path(executable).is_file())


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(float(value), maximum))


PROBE_ADAPTERS = {
    "jira": probe_jira,
    "teamcenter": probe_teamcenter,
    "doors": probe_doors,
    "docproof": probe_docproof,
    "office": probe_office,
    "ai": probe_ai,
    "media": probe_media,
}
