from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ModelReference:
    """Identify a Teamcenter model object."""

    uid: str
    type: str = "WorkspaceObject"

    def to_json(self) -> dict[str, str]:
        """Return the Teamcenter wire representation."""
        return {"uid": self.uid, "type": self.type}


@dataclass(frozen=True, slots=True)
class PropertyUpdate:
    """Represent a Teamcenter property update."""

    name: str
    values: tuple[str, ...]

    @classmethod
    def many(cls, name: str, values: Iterable[str]) -> "PropertyUpdate":
        """Create an update containing one or more string values."""
        return cls(name=name, values=tuple(values))

    def to_json(self) -> dict[str, object]:
        """Return the Teamcenter wire representation."""
        return {"name": self.name, "values": list(self.values)}
