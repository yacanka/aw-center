from dataclasses import dataclass
from pathlib import Path


class JobCancelled(Exception):
    """Signal cooperative cancellation without exposing internal errors."""


class JobLeaseLost(Exception):
    """Stop an executor whose claim is no longer allowed to publish state."""


class JobExecutionFailure(Exception):
    """Represent a sanitized worker failure with a stable code."""

    def __init__(self, message, code="JOB_EXECUTION_FAILED", retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class JobExecutionUncertain(Exception):
    """Stop automatic retries when an external write may have been committed."""

    def __init__(self, message="Confirm the external system state before continuing."):
        super().__init__(message)
        self.code = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class JobExecutionResult:
    """Describe a completed artifact produced by a job executor."""

    path: Path
    filename: str
    message: str = "Completed successfully."
    summary: dict | None = None
