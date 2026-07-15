import time
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import requests

from .config import TeamcenterClientConfig
from .exceptions import (
    TeamcenterAuthenticationError,
    TeamcenterConnectionError,
    TeamcenterProtocolError,
)
from .protocol import make_envelope
from .response import parse_teamcenter_response


class TeamcenterTransport:
    """Send bounded, TLS-aware requests to Teamcenter SOA endpoints."""

    def __init__(self, config: TeamcenterClientConfig, session=None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update(self.default_headers())
        if config.csrf_token:
            self.set_csrf_token(config.csrf_token)

    @staticmethod
    def default_headers() -> dict[str, str]:
        """Return headers shared by all Teamcenter requests."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "aw-center-teamcenter/0.2.0",
        }

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    def service_url(self, service: str) -> str:
        """Build an absolute URL for an allowlisted SOA service path."""
        root = f"{self.config.base_url}/{self.config.service_root}/"
        return urljoin(root, service.lstrip("/"))

    def cookie_value(self, name: str) -> str | None:
        """Return the most specific matching cookie value."""
        host = (urlsplit(self.config.base_url).hostname or "").lower()
        matches = [cookie for cookie in self.session.cookies if cookie.name == name]
        if not matches:
            return None
        selected = max(matches, key=lambda item: self.cookie_score(item, host))
        return str(selected.value)

    @staticmethod
    def cookie_score(cookie, host: str) -> tuple[int, int]:
        """Score a cookie by domain and path specificity."""
        domain = (cookie.domain or "").lstrip(".").lower()
        domain_match = int(not domain or domain == host or host.endswith(f".{domain}"))
        return domain_match, len(cookie.path or "")

    @property
    def csrf_token(self) -> str | None:
        """Return the current CSRF token from a header or cookie."""
        header = self.session.headers.get(self.config.csrf_header_name)
        cookie = self.cookie_value(self.config.csrf_cookie_name)
        return str(header) if header else unquote(cookie) if cookie else None

    def set_csrf_token(self, token: str) -> None:
        """Install a normalized CSRF request header."""
        normalized = unquote(token.strip())
        if normalized:
            self.session.headers[self.config.csrf_header_name] = normalized

    def sync_csrf_token(self, response=None) -> str | None:
        """Adopt a CSRF token returned by Teamcenter."""
        candidates = self.response_token_candidates(response)
        for candidate in candidates:
            if candidate:
                self.set_csrf_token(str(candidate))
                break
        return self.csrf_token

    def response_token_candidates(self, response) -> list[str | None]:
        """Return response and cookie CSRF token candidates."""
        headers = response.headers if response is not None else {}
        return [
            headers.get(self.config.csrf_header_name),
            headers.get("X-CSRF-TOKEN"),
            self.cookie_value(self.config.csrf_cookie_name),
        ]

    def bootstrap_csrf(self) -> str:
        """Bootstrap Teamcenter's session-bound XSRF cookie."""
        response = self.get_bootstrap_response()
        try:
            return self.extract_bootstrap_token(response)
        finally:
            response.close()

    def get_bootstrap_response(self):
        """Request the Teamcenter context root without buffering its body."""
        url = f"{self.config.base_url}/"
        try:
            return self.session.get(
                url,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
                headers={"Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
                stream=True,
            )
        except requests.RequestException as error:
            raise TeamcenterConnectionError("Teamcenter CSRF bootstrap failed.") from error

    def extract_bootstrap_token(self, response) -> str:
        """Validate a bootstrap response and return its XSRF token."""
        if response.status_code >= 400:
            raise TeamcenterProtocolError("Teamcenter CSRF bootstrap was rejected.")
        token = self.sync_csrf_token(response)
        if not token:
            raise TeamcenterAuthenticationError("Teamcenter did not issue an XSRF token.")
        return token

    def call(self, service: str, body: dict[str, Any], *, idempotent: bool) -> dict[str, Any]:
        """Call a Teamcenter SOA service."""
        if not self.csrf_token:
            self.bootstrap_csrf()
        return self.post_json(self.service_url(service), make_envelope(body), idempotent)

    def post_json(self, url: str, payload: dict[str, Any], idempotent: bool) -> dict[str, Any]:
        """POST JSON with bounded retries for read-only calls."""
        attempts = 1 + (self.config.max_read_retries if idempotent else 0)
        for attempt in range(attempts):
            response = self.send(url, payload, attempt, attempts)
            if response is None:
                continue
            return self.parse_response(response)
        raise TeamcenterConnectionError("Teamcenter request failed after retries.")

    def send(self, url: str, payload: dict[str, Any], attempt: int, attempts: int):
        """Send one request attempt and decide whether to retry."""
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
                stream=True,
            )
        except requests.RequestException as error:
            return self.handle_request_error(error, attempt, attempts)
        self.sync_csrf_token(response)
        if response.status_code in {429, 502, 503, 504} and attempt + 1 < attempts:
            response.close()
            self.backoff(attempt)
            return None
        return response

    def handle_request_error(self, error, attempt: int, attempts: int):
        """Retry a transient request failure or raise a safe error."""
        if attempt + 1 < attempts:
            self.backoff(attempt)
            return None
        raise TeamcenterConnectionError("Teamcenter could not be reached.") from error

    def backoff(self, attempt: int) -> None:
        """Apply exponential retry backoff."""
        time.sleep(self.config.retry_backoff_seconds * (2**attempt))

    def parse_response(self, response) -> dict[str, Any]:
        """Validate and parse a Teamcenter JSON response."""
        return parse_teamcenter_response(response, self.config.max_response_bytes)
