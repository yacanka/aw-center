from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .exceptions import TeamcenterConfigurationError


class AuthMode(StrEnum):
    """Supported Teamcenter authentication modes."""

    PASSWORD = "password"
    COOKIE = "cookie"


@dataclass(frozen=True, slots=True)
class EndpointCatalog:
    """Define the supported Teamcenter SOA contracts."""

    login: str = "Core-2011-06-Session/login"
    logout: str = "Core-2006-03-Session/logout"
    find_saved_queries: str = "Core-2006-03-Query/findSavedQueries"
    execute_saved_queries: str = "Core-2007-06-Query/executeSavedQueries"
    load_objects: str = "Core-2006-03-DataManagement/loadObjects"
    get_properties: str = "Core-2006-03-DataManagement/getProperties"
    set_properties: str = "Core-2007-01-DataManagement/setProperties"


@dataclass(slots=True)
class TeamcenterClientConfig:
    """Hold validated Teamcenter connection configuration."""

    base_url: str
    auth_mode: AuthMode = AuthMode.PASSWORD
    username: str = ""
    password: str = ""
    group: str = ""
    role: str = ""
    service_root: str = "RestServices"
    verify_ssl: bool | str = True
    jsessionid: str = ""
    csrf_token: str = ""
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0
    max_read_retries: int = 2
    max_response_bytes: int = 10 * 1024 * 1024
    retry_backoff_seconds: float = 0.5
    csrf_cookie_name: str = "XSRF-TOKEN"
    csrf_header_name: str = "X-XSRF-TOKEN"
    endpoints: EndpointCatalog = field(default_factory=EndpointCatalog)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.service_root = self.service_root.strip("/")
        self.validate()

    @property
    def timeout(self) -> tuple[float, float]:
        """Return requests-compatible connect and read timeouts."""
        return self.connect_timeout_seconds, self.read_timeout_seconds

    def validate(self) -> None:
        """Validate required configuration without exposing secrets."""
        if not self.base_url.startswith(("http://", "https://")):
            raise TeamcenterConfigurationError("TEAMCENTER_BASE_URL must be an HTTP(S) URL.")
        if not self.service_root:
            raise TeamcenterConfigurationError("TEAMCENTER_SERVICE_ROOT cannot be empty.")
        if self.auth_mode is AuthMode.PASSWORD and (not self.username or not self.password):
            raise TeamcenterConfigurationError("Teamcenter username and password are required.")
        if self.auth_mode is AuthMode.COOKIE and not self.jsessionid:
            raise TeamcenterConfigurationError("TEAMCENTER_JSESSIONID is required in cookie mode.")
        if isinstance(self.verify_ssl, str) and not Path(self.verify_ssl).is_file():
            raise TeamcenterConfigurationError("The Teamcenter CA bundle does not exist.")
        if not 0 < self.connect_timeout_seconds <= 60 or not 0 < self.read_timeout_seconds <= 300:
            raise TeamcenterConfigurationError("Teamcenter timeouts are outside allowed bounds.")
        if not 0 <= self.max_read_retries <= 5:
            raise TeamcenterConfigurationError("Teamcenter read retries must be between 0 and 5.")
        if not 1024 <= self.max_response_bytes <= 100 * 1024 * 1024:
            raise TeamcenterConfigurationError("Teamcenter response limit is outside allowed bounds.")
