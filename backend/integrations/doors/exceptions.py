"""Sanitized DOORS adapter exceptions."""


class DoorsError(RuntimeError):
    """Base IBM Rational DOORS integration error."""

    code = "DOORS_OPERATION_FAILED"


class DoorsConnectionError(DoorsError):
    """Raised when the DOORS OLE client cannot be reached."""

    def __init__(self, message, code="DOORS_CONNECTION_FAILED"):
        super().__init__(message)
        self.code = code


class DoorsDxlError(DoorsError):
    """Raised when DXL execution fails."""

    code = "DOORS_DXL_FAILED"


class DoorsConfigurationError(DoorsConnectionError):
    """Reject invalid local settings before attempting a DOORS operation."""

    def __init__(self):
        super().__init__("DOORS client configuration is invalid.", "DOORS_CONFIG_INVALID")


class DoorsOperationError(DoorsError):
    """Raised when a high-level DOORS operation reports an error."""

    def __init__(self, message: str, code: str = "DOORS_OPERATION_FAILED") -> None:
        """Store a stable operation code with the user-facing reason."""
        super().__init__(message)
        self.code = code
