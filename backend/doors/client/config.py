from dataclasses import dataclass
from pathlib import Path

RESULT_MODE_APPLICATION = "application_result"
RESULT_MODE_FILE = "file"
RESULT_MODES = frozenset({RESULT_MODE_APPLICATION, RESULT_MODE_FILE})


@dataclass(frozen=True, slots=True)
class DoorsClientConfig:
    """Hold IBM Rational DOORS OLE connection configuration."""

    executable_path: str
    database: str = ""
    ole_program_id: str = "DOORS.Application"
    prefer_active_instance: bool = True
    auto_start_client: bool = False
    startup_timeout_seconds: float = 30.0
    run_timeout_seconds: float = 120.0
    max_result_bytes: int = 10 * 1024 * 1024
    result_mode: str = RESULT_MODE_FILE

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

    @property
    def executable(self) -> Path:
        """Return the configured executable as a path."""
        return Path(self.executable_path)
