"""Fail-closed system checks for the supported production topology."""

from urllib.parse import urlparse, urlsplit

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, register
from django.http.request import validate_host

from awcenter.outbound_urls import normalize_outbound_base_url


PLACEHOLDER_SECRETS = {
    "",
    "change-me",
    "changeme",
    "replace-me",
    "your-secret-key",
    "aw-center-local-development-secret-key-change-before-production-2026",
}


@register(Tags.security, deploy=True)
def production_runtime_checks(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    errors = []
    database_engine = settings.DATABASES["default"]["ENGINE"]
    if database_engine != "django.db.backends.postgresql":
        errors.append(
            Error(
                "Production requires PostgreSQL for transaction and lease semantics.",
                id="awcenter.E001",
            )
        )
    cache_backend = settings.CACHES["default"]["BACKEND"]
    if "redis" not in cache_backend.casefold():
        errors.append(
            Error(
                "Production requires a process-shared Redis cache.",
                id="awcenter.E002",
            )
        )
    normalized_secret = settings.SECRET_KEY.strip().casefold()
    if (
        len(settings.SECRET_KEY) < 50
        or normalized_secret in PLACEHOLDER_SECRETS
        or normalized_secret.startswith("replace-")
    ):
        errors.append(Error("SECRET_KEY is missing or a placeholder.", id="awcenter.E003"))
    if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
        errors.append(
            Error(
                "Production session and CSRF cookies must be Secure.",
                id="awcenter.E004",
            )
        )
    if settings.SESSION_COOKIE_SAMESITE not in {"Lax", "Strict"}:
        errors.append(
            Error(
                "The same-origin browser session requires SameSite=Lax or Strict.",
                id="awcenter.E005",
            )
        )
    if "*" in settings.ALLOWED_HOSTS:
        errors.append(
            Error("Production ALLOWED_HOSTS cannot contain a wildcard.", id="awcenter.E006")
        )
    if not settings.TRUST_PROXY_HEADERS or settings.TRUSTED_PROXY_COUNT < 1:
        errors.append(
            Error(
                "The supported Nginx topology requires explicit proxy-header trust.",
                id="awcenter.E007",
            )
        )
    if settings.STATIC_ROOT.resolve() == settings.BASE_DIR.resolve():
        errors.append(
            Error("STATIC_ROOT cannot be the backend source root.", id="awcenter.E008")
        )
    if settings.PRIVATE_MEDIA_ROOT.resolve().is_relative_to(settings.STATIC_ROOT.resolve()):
        errors.append(
            Error("Private artifacts cannot be stored under STATIC_ROOT.", id="awcenter.E009")
        )
    errors.extend(_frontend_capability_url_checks())
    errors.extend(_integration_checks())
    return errors


def _frontend_capability_url_checks():
    checks = []
    for setting_name, expected_path, error_id in (
        ("FRONTEND_RESET_URL", "/app/login", "awcenter.E025"),
        ("FRONTEND_INVITATION_URL", "/app/invite", "awcenter.E026"),
    ):
        value = getattr(settings, setting_name, "")
        if _valid_frontend_capability_url(value, expected_path):
            continue
        checks.append(
            Error(
                f"{setting_name} must be a credential-free HTTPS URL for "
                f"{expected_path} on an ALLOWED_HOSTS origin, without query or fragment.",
                id=error_id,
            )
        )
    return checks


def _valid_frontend_capability_url(value, expected_path):
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if "?" in value or "#" in value:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
        or (port is not None and port < 1)
        or parsed.netloc.rsplit("@", 1)[-1].endswith(":")
    ):
        return False
    hostname = parsed.hostname.rstrip(".").casefold()
    validation_host = f"[{hostname}]" if ":" in hostname else hostname
    return validate_host(validation_host, settings.ALLOWED_HOSTS)


def _integration_checks():
    checks = []
    for enabled_name, url_name, code in (
        ("JIRA_ENABLED", "JIRA_URL", "awcenter.E010"),
        ("DOCPROOF_ENABLED", "DOCPROOF_URL", "awcenter.E011"),
        ("TEAMCENTER_ENABLED", "TEAMCENTER_BASE_URL", "awcenter.E012"),
    ):
        if not getattr(settings, enabled_name, False):
            continue
        value = getattr(settings, url_name, "")
        try:
            normalize_outbound_base_url(value, require_https=True)
        except ValueError:
            checks.append(Error(f"{url_name} must be an HTTPS URL.", id=code))
    if settings.JIRA_ENABLED and not settings.JIRA_SESSION_ENCRYPTION_KEY:
        checks.append(
            Error(
                "JIRA_SESSION_ENCRYPTION_KEY is required when JIRA is enabled.",
                id="awcenter.E013",
            )
        )
    elif settings.JIRA_ENABLED:
        try:
            Fernet(settings.JIRA_SESSION_ENCRYPTION_KEY.encode("ascii"))
        except (TypeError, ValueError, UnicodeError):
            checks.append(
                Error(
                    "JIRA_SESSION_ENCRYPTION_KEY must be a valid Fernet key.",
                    id="awcenter.E018",
                )
            )
    if settings.DOCPROOF_ENABLED:
        if not settings.DOCPROOF_USERNAME or not settings.DOCPROOF_PASSWORD:
            checks.append(
                Error(
                    "DocProof credentials are required when DocProof is enabled.",
                    id="awcenter.E019",
                )
            )
        if (
            not settings.DOCPROOF_VERIFY_SSL
            and not settings.DOCPROOF_CERTIFICATE_FILE.is_file()
        ):
            checks.append(
                Error(
                    "DocProof TLS verification cannot be disabled in production.",
                    id="awcenter.E020",
                )
            )
    if settings.TEAMCENTER_ENABLED and settings.TEAMCENTER_VERIFY_SSL is False:
        checks.append(
            Error(
                "Teamcenter TLS verification cannot be disabled in production.",
                id="awcenter.E021",
            )
        )
    if settings.DOORS_ENABLED:
        from automations.identity import valid_runner_token

        if not valid_runner_token(settings.DOORS_RUNNER_TOKEN):
            checks.append(
                Error(
                    "DOORS requires a valid host-local runner token.",
                    id="awcenter.E014",
                )
            )
    if settings.ASSESSMENT_API_URL:
        parsed_assessment = urlparse(settings.ASSESSMENT_API_URL)
        if (
            parsed_assessment.scheme != "https"
            or not parsed_assessment.hostname
            or parsed_assessment.hostname not in settings.ASSESSMENT_API_ALLOWED_HOSTS
        ):
            checks.append(
                Error(
                    "Assessment API requires HTTPS and an explicit host allowlist.",
                    id="awcenter.E023",
                )
            )
    if (
        settings.AWCENTER_MAIL_TRANSPORT == "django"
        and not settings.EMAIL_USE_TLS
        and not settings.EMAIL_USE_SSL
    ):
        checks.append(
            Error(
                "Production SMTP transport requires TLS or SSL.",
                id="awcenter.E024",
            )
        )
    return checks
