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

    PUBLIC_MESSAGES = {
        "invalid_result": "DOORS returned an invalid operation result. Check the result format and client compatibility.",
        "empty_result": "DOORS returned an empty operation result.",
        "incomplete_result": "DOORS did not return the operation completion marker. The export may be incomplete.",
        "result_timeout": "DOORS did not publish a matching result before the configured timeout.",
        "result_too_large": "The DOORS result exceeded the configured size limit. Reduce the export size.",
        "invalid_encoding": "DOORS returned a result that is not valid UTF-8.",
        "result_file_unavailable": "The DOORS result file could not be created or read. Check the worker's temporary directory access.",
        "ole_call_failed": "The DOORS OLE execution call failed. Check the client session and open dialogs.",
    }

    def __init__(self, message, *, reason="invalid_result"):
        super().__init__(message)
        # Never expose upstream exception text, module paths or object values.
        self.public_message = self.PUBLIC_MESSAGES.get(reason, self.PUBLIC_MESSAGES["invalid_result"])


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
