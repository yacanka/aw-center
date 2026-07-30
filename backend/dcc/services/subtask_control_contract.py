"""Stable value contract returned by project-specific DCC controls."""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SubtaskControlResult:
    """Describe controlled subtasks, project context, and field overrides."""

    subtasks: tuple[Any, ...]
    render_context: Mapping[str, Any] = field(default_factory=dict)
    placeholder_overrides: Mapping[str, str] = field(default_factory=dict)
