"""Repository-owned Django and npm quality commands."""

from __future__ import annotations

import json

from .model import LauncherError, Project
from .process import required_tool, run


def django(project: Project, arguments: list[str], extra_env: dict[str, str] | None = None) -> None:
    """Run one Django management command using the project virtual environment."""
    run([project.python, "manage.py", *arguments], project.backend, extra_env=extra_env)


def package_scripts(project: Project) -> dict[str, str]:
    """Read string-valued npm scripts from the Vue manifest."""
    manifest = json.loads(project.package_json.read_text(encoding="utf-8"))
    scripts = manifest.get("scripts", {})
    return {key: value for key, value in scripts.items() if isinstance(value, str)}


def select_script(
    project: Project, candidates: tuple[str, ...], *, required: bool = False
) -> str | None:
    """Select the first repository-owned npm script from a preference list."""
    scripts = package_scripts(project)
    selected = next((name for name in candidates if name in scripts), None)
    if required and not selected:
        raise LauncherError(f"no npm script found; expected one of: {', '.join(candidates)}")
    return selected


def run_first_script(project: Project, candidates: tuple[str, ...]) -> None:
    """Run the first available script or report a deliberate skip."""
    script = select_script(project, candidates)
    if script:
        run_script(project, script)
    else:
        print(f"[skip] no npm script found for {', '.join(candidates)}")


def run_script(project: Project, script: str) -> None:
    """Run one npm script from the discovered Vue directory."""
    if script not in package_scripts(project):
        raise LauncherError(f"npm script is missing: {script}")
    run([required_tool("npm"), "run", script], project.frontend)
