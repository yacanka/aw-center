"""DOORS adapter configuration."""

from dataclasses import dataclass, field
from pathlib import Path

RESULT_MODE_APPLICATION = "application_result"
RESULT_MODE_FILE = "file"
RESULT_MODES = frozenset({RESULT_MODE_APPLICATION, RESULT_MODE_FILE})


@dataclass(frozen=True, slots=True)
class DoorsClientConfig:
    """Hold IBM Rational DOORS OLE connection configuration."""

    executable_path: str = ""
    database: str = ""
    ole_program_id: str = "DOORS.Application"
    prefer_active_instance: bool = True
    auto_start_client: bool = True
    startup_timeout_seconds: float = 90.0
    run_timeout_seconds: float = 120.0
    max_result_bytes: int = 10 * 1024 * 1024
    result_mode: str = RESULT_MODE_FILE
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        """Validate bounded timeout and result-size configuration."""
        if not 0 < self.startup_timeout_seconds <= 300:
            raise ValueError("DOORS startup timeout must be between 0 and 300 seconds.")
        if not 0 < self.run_timeout_seconds <= 600:
            raise ValueError("DOORS run timeout must be between 0 and 600 seconds.")
        if not 1024 <= self.max_result_bytes <= 100 * 1024 * 1024:
            raise ValueError("DOORS result limit must be between 1 KB and 100 MB.")
        if self.result_mode not in RESULT_MODES:
            raise ValueError("DOORS result mode must be file or application_result.")
        if not self.ole_program_id.strip():
            raise ValueError("DOORS OLE program ID is required.")
        if self.password and not self.username:
            raise ValueError("DOORS username is required when a password is configured.")
        if any("\x00" in value for value in (
            self.executable_path, self.database, self.ole_program_id,
            self.username, self.password,
        )):
            raise ValueError("DOORS configuration contains an invalid character.")

    @property
    def executable(self) -> Path:
        """Return the configured executable as a path."""
        return Path(self.executable_path)
