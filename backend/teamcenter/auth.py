from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlsplit

from .config import AuthMode, TeamcenterClientConfig
from .exceptions import TeamcenterConfigurationError
from .transport import TeamcenterTransport


class Authenticator(ABC):
    """Define Teamcenter authentication behavior."""

    @abstractmethod
    def login(self) -> dict[str, Any]:
        """Authenticate the configured Teamcenter session."""

    @abstractmethod
    def logout(self) -> None:
        """Clear or terminate the configured Teamcenter session."""


class PasswordAuthenticator(Authenticator):
    """Authenticate with server-side Teamcenter credentials."""

    def __init__(self, config: TeamcenterClientConfig, transport: TeamcenterTransport) -> None:
        self.config = config
        self.transport = transport

    def login(self) -> dict[str, Any]:
        """Bootstrap CSRF and call the Teamcenter login service."""
        self.transport.bootstrap_csrf()
        credentials = {
            "user": self.config.username,
            "password": self.config.password,
            "group": self.config.group,
            "role": self.config.role,
            "locale": "en_US",
            "descrimator": "",
        }
        return self.transport.call(
            self.config.endpoints.login, {"credentials": credentials}, idempotent=False
        )

    def logout(self) -> None:
        """Call logout and always clear local credentials."""
        try:
            self.transport.call(self.config.endpoints.logout, {}, idempotent=False)
        finally:
            clear_session(self.config, self.transport)


class CookieAuthenticator(Authenticator):
    """Reuse a server-configured JSESSIONID/XSRF pair."""

    def __init__(self, config: TeamcenterClientConfig, transport: TeamcenterTransport) -> None:
        self.config = config
        self.transport = transport

    def login(self) -> dict[str, Any]:
        """Install configured cookies and synchronize the CSRF header."""
        domain = urlsplit(self.config.base_url).hostname
        self.transport.session.cookies.set("JSESSIONID", self.config.jsessionid, domain=domain, path="/")
        if self.config.csrf_token:
            self.transport.session.cookies.set(
                self.config.csrf_cookie_name, self.config.csrf_token, domain=domain, path="/"
            )
            self.transport.set_csrf_token(self.config.csrf_token)
        else:
            self.transport.bootstrap_csrf()
        return {"cookieAuthentication": True, "csrfReady": bool(self.transport.csrf_token)}

    def logout(self) -> None:
        """Clear locally configured cookie credentials."""
        clear_session(self.config, self.transport)


def clear_session(config: TeamcenterClientConfig, transport: TeamcenterTransport) -> None:
    """Remove all session cookies and the CSRF header."""
    transport.session.cookies.clear()
    transport.session.headers.pop(config.csrf_header_name, None)


def create_authenticator(config, transport) -> Authenticator:
    """Create the authenticator selected by configuration."""
    if config.auth_mode is AuthMode.PASSWORD:
        return PasswordAuthenticator(config, transport)
    if config.auth_mode is AuthMode.COOKIE:
        return CookieAuthenticator(config, transport)
    raise TeamcenterConfigurationError("Unsupported Teamcenter authentication mode.")
