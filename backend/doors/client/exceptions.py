class DoorsError(RuntimeError):
    """Base IBM Rational DOORS integration error."""


class DoorsConnectionError(DoorsError):
    """Raised when the DOORS OLE client cannot be reached."""


class DoorsDxlError(DoorsError):
    """Raised when DXL execution fails."""


class DoorsOperationError(DoorsError):
    """Raised when a high-level DOORS operation reports an error."""
