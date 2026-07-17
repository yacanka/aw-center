from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Represent a high-level DXL operation result."""

    ok: bool
    message: str = ""
    raw_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DoorsObject:
    """Represent an IBM Rational DOORS object."""

    absolute_number: int
    identifier: str = ""
    level: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable API representation."""
        return {
            "absolute_number": self.absolute_number,
            "identifier": self.identifier,
            "level": self.level,
            "attributes": self.attributes,
        }
