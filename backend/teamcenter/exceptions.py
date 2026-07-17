from dataclasses import dataclass
from typing import Any


class TeamcenterError(RuntimeError):
    """Base Teamcenter integration error."""


class TeamcenterConfigurationError(TeamcenterError):
    """Raised when Teamcenter configuration is invalid."""


class TeamcenterConnectionError(TeamcenterError):
    """Raised when the Teamcenter web tier cannot be reached."""


class TeamcenterAuthenticationError(TeamcenterError):
    """Raised when Teamcenter authentication fails."""


class TeamcenterProtocolError(TeamcenterError):
    """Raised when Teamcenter returns an invalid response."""


@dataclass(frozen=True, slots=True)
class PartialErrorDetail:
    """Represent one Teamcenter SOA partial error."""

    code: int | str | None
    messages: tuple[str, ...]
    raw: dict[str, Any]


class TeamcenterServiceError(TeamcenterError):
    """Raised when Teamcenter reports SOA partial errors."""

    def __init__(self, errors: list[PartialErrorDetail]) -> None:
        self.errors = errors
        super().__init__("Teamcenter reported one or more service errors.")
