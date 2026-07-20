"""Launcher data models."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Project:
    """Discovered Django and Vue project paths."""

    root: Path
    manage_py: Path
    package_json: Path
    requirements: Path | None

    @property
    def backend(self) -> Path:
        """Return the Django working directory."""
        return self.manage_py.parent

    @property
    def frontend(self) -> Path:
        """Return the frontend working directory."""
        return self.package_json.parent

    @property
    def venv(self) -> Path:
        """Return the conventional project virtual environment."""
        return self.root / ".venv"

    @property
    def python(self) -> Path:
        """Return the virtual environment Python executable."""
        directory = "Scripts" if os.name == "nt" else "bin"
        executable = "python.exe" if os.name == "nt" else "python"
        return self.venv / directory / executable


@dataclass(frozen=True)
class Scope:
    """Select the backend and frontend sides of a workflow."""

    backend: bool = True
    frontend: bool = True

    def require_any(self) -> None:
        """Reject a workflow with both project sides disabled."""
        if not self.backend and not self.frontend:
            raise LauncherError("both backend and frontend were skipped")


class LauncherError(RuntimeError):
    """Expected launcher failure with a user-actionable message."""
