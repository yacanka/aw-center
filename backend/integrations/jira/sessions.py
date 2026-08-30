"""Owner-scoped encrypted cache for ephemeral JIRA sessions."""

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from jira import JIRAError

from .client import JiraConfigurationError, JiraConnector, validated_session_id

CACHE_KEY_PREFIX = "integrations:jira-session:v1"
LEGACY_CREDENTIAL_KEYS = frozenset({"jsessionid", "sessionid", "jira_session_id"})


class JiraSessionError(RuntimeError):
    """Base safe error for JIRA session lifecycle operations."""

    detail = "The JIRA session is unavailable."
    code = "JIRA_SESSION_UNAVAILABLE"
    response_status = 503


class JiraSessionConfigurationError(JiraSessionError):
    detail = "JIRA session storage is not configured safely."
    code = "JIRA_SESSION_CONFIGURATION_ERROR"


class JiraSessionNotConnected(JiraSessionError):
    detail = "Connect a JIRA session before continuing."
    code = "JIRA_SESSION_REQUIRED"
    response_status = 409


class JiraSessionInvalid(JiraSessionError):
    detail = "The JIRA session is invalid."
    code = "JIRA_SESSION_INVALID"
    response_status = 400


class JiraSessionUpstreamError(JiraSessionError):
    detail = "JIRA session validation is unavailable."
    code = "JIRA_SESSION_UNAVAILABLE"
    response_status = 502


@dataclass(frozen=True)
class JiraSessionRecord:
    credential: str
    identity: dict
    expires_at: str

    def public_payload(self):
        return {
            "state": "connected",
            "expires_at": self.expires_at,
        }


def connect_jira_session(owner, credential):
    """Validate, encrypt, and cache one owner's replaceable JIRA session."""

    ensure_jira_enabled()
    try:
        normalized = validated_session_id(credential)
    except ValueError as error:
        raise JiraSessionInvalid() from error
    try:
        connector = JiraConnector(settings.JIRA_URL, jira_session_id=normalized)
        identity = sanitize_jira_identity(connector.current_user())
    except JiraConfigurationError as error:
        raise JiraSessionConfigurationError() from error
    except JIRAError as error:
        if jira_status_code(error) in {401, 403}:
            raise JiraSessionInvalid() from error
        raise JiraSessionUpstreamError() from error
    except Exception as error:
        raise JiraSessionUpstreamError() from error
    if not identity:
        raise JiraSessionInvalid()
    return store_jira_session(owner, normalized, identity)


def get_jira_session(owner):
    """Decrypt an owned session, clearing corrupt or expired cache entries."""

    key = owner_cache_key(owner)
    encrypted = cache.get(key)
    if not encrypted:
        return None
    try:
        decoded = session_cipher().decrypt(str(encrypted).encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        record = JiraSessionRecord(
            credential=validated_session_id(payload["credential"]),
            identity=sanitize_cached_identity(payload["identity"]),
            expires_at=str(payload["expires_at"]),
        )
        if datetime.fromisoformat(record.expires_at) <= timezone.now():
            clear_jira_session(owner)
            return None
        return record
    except (InvalidToken, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        clear_jira_session(owner)
        return None


def require_jira_session(owner):
    record = get_jira_session(owner)
    if record is None:
        raise JiraSessionNotConnected()
    return record


def jira_connector_for(owner):
    """Build a request-local adapter from the owner's encrypted cached credential."""

    ensure_jira_enabled()
    record = require_jira_session(owner)
    try:
        return JiraConnector(settings.JIRA_URL, jira_session_id=record.credential)
    except (JiraConfigurationError, ValueError) as error:
        raise JiraSessionConfigurationError() from error
    except JIRAError as error:
        raise JiraSessionUpstreamError() from error


def store_jira_session(owner, credential, identity):
    ttl = session_ttl_seconds()
    expires_at = timezone.now() + timedelta(seconds=ttl)
    record = JiraSessionRecord(
        credential=credential,
        identity=sanitize_cached_identity(identity),
        expires_at=expires_at.isoformat(),
    )
    serialized = json.dumps(
        {
            "credential": record.credential,
            "identity": record.identity,
            "expires_at": record.expires_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encrypted = session_cipher().encrypt(serialized).decode("ascii")
    cache.set(owner_cache_key(owner), encrypted, timeout=ttl)
    return record


def clear_jira_session(owner):
    """Delete one user's JIRA credential; safe for logout and repeated calls."""

    owner_id = owner_identifier(owner, required=False)
    if owner_id is not None:
        cache.delete(f"{CACHE_KEY_PREFIX}:{owner_id}")


def has_legacy_jira_credential(value):
    """Detect credential fields so non-canonical endpoints can reject them."""

    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in LEGACY_CREDENTIAL_KEYS
            or has_legacy_jira_credential(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(has_legacy_jira_credential(item) for item in value)
    return False


def owner_cache_key(owner):
    return f"{CACHE_KEY_PREFIX}:{owner_identifier(owner)}"


def owner_identifier(owner, required=True):
    value = getattr(owner, "pk", owner)
    if value is None or isinstance(value, bool):
        if required:
            raise JiraSessionConfigurationError()
        return None
    return str(value)


def session_ttl_seconds():
    try:
        ttl = int(settings.JIRA_SESSION_TTL_SECONDS)
    except (TypeError, ValueError) as error:
        raise JiraSessionConfigurationError() from error
    if not 1 <= ttl <= 24 * 60 * 60:
        raise JiraSessionConfigurationError()
    return ttl


def session_cipher():
    """Return a stable Fernet cipher; production never derives its own key."""

    configured = str(settings.JIRA_SESSION_ENCRYPTION_KEY or "").strip()
    if not configured:
        if not settings.DEBUG:
            raise JiraSessionConfigurationError()
        digest = hashlib.sha256(
            f"awcenter:jira-session:{settings.SECRET_KEY}".encode("utf-8")
        ).digest()
        configured = base64.urlsafe_b64encode(digest).decode("ascii")
    try:
        return Fernet(configured.encode("ascii"))
    except (TypeError, ValueError, UnicodeError) as error:
        raise JiraSessionConfigurationError() from error


def ensure_jira_enabled():
    if not settings.JIRA_ENABLED:
        raise JiraSessionConfigurationError()
    if not settings.DEBUG:
        cache_backend = settings.CACHES["default"]["BACKEND"]
        if "redis" not in cache_backend.casefold():
            raise JiraSessionConfigurationError()


def sanitize_jira_identity(value):
    if not isinstance(value, Mapping):
        return {}
    username = value.get("name") or value.get("key") or value.get("accountId")
    display_name = value.get("displayName") or username
    if not username and not display_name:
        return {}
    return {
        "username": str(username or "")[:255],
        "display_name": str(display_name or "")[:255],
    }


def sanitize_cached_identity(value):
    if not isinstance(value, Mapping):
        raise ValueError("Invalid cached JIRA identity.")
    username = str(value.get("username") or "")[:255]
    display_name = str(value.get("display_name") or username)[:255]
    if not username and not display_name:
        raise ValueError("Invalid cached JIRA identity.")
    return {"username": username, "display_name": display_name}


def jira_status_code(error):
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None
