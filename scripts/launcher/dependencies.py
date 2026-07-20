"""Backend/frontend dependency and offline-cache workflows."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from .model import LauncherError, Project, Scope
from .process import required_tool, run

MINIMUM_PYTHON = (3, 11)


def ensure_launcher_python() -> None:
    """Require a supported interpreter before creating a virtual environment."""
    if sys.version_info[:2] < MINIMUM_PYTHON:
        raise LauncherError("Python 3.11 or newer is required")


def ensure_virtual_environment(project: Project, *, create: bool) -> None:
    """Create or validate the project-local virtual environment."""
    ensure_launcher_python()
    if project.python.is_file():
        check_virtual_environment_version(project)
        return
    if not create:
        raise LauncherError(".venv is missing; run `python launcher.py setup`")
    if project.venv.exists():
        raise LauncherError(f"incomplete virtual environment: {project.venv}")
    run([sys.executable, "-m", "venv", project.venv], project.root)
    check_virtual_environment_version(project)


def check_virtual_environment_version(project: Project) -> None:
    """Reject stale virtual environments created by unsupported Python versions."""
    script = "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    completed = run([project.python, "-c", script], project.root, capture=True)
    version = tuple(int(part) for part in completed.stdout.strip().split("."))
    if version[:2] < MINIMUM_PYTHON:
        rendered = ".".join(str(part) for part in version)
        raise LauncherError(f".venv uses unsupported Python {rendered}; recreate it with Python 3.11+")


def install(project: Project, scope: Scope, mode: str, offline_dir: Path) -> None:
    """Install selected project dependencies from online or prepared sources."""
    scope.require_any()
    if scope.backend:
        install_backend(project, mode, offline_dir)
    if scope.frontend:
        install_frontend(project, mode, offline_dir)


def install_backend(project: Project, mode: str, offline_dir: Path) -> None:
    """Install backend requirements into the project virtual environment."""
    if not project.requirements:
        raise LauncherError("requirements.txt was not found")
    ensure_virtual_environment(project, create=True)
    command: list[str | Path] = [project.python, "-m", "pip", "install"]
    if mode == "offline":
        require_files(offline_dir / "wheels", "offline Python wheels")
        command += ["--no-index", "--find-links", offline_dir / "wheels"]
    command += ["-r", project.requirements]
    run(command, project.root)
    run([project.python, "-m", "pip", "check"], project.root)


def install_frontend(project: Project, mode: str, offline_dir: Path) -> None:
    """Install frontend dependencies with the repository-selected npm mode."""
    npm = required_tool("npm")
    command: list[str | Path] = [npm, npm_install_action(project)]
    if mode == "offline":
        require_files(offline_dir / "npm-cache", "offline npm cache")
        command += ["--offline", "--cache", offline_dir / "npm-cache"]
    run(command, project.frontend)


def prepare_offline(project: Project, scope: Scope, offline_dir: Path) -> None:
    """Download Python artifacts and populate an npm cache for offline setup."""
    scope.require_any()
    if scope.backend:
        if not project.requirements:
            raise LauncherError("requirements.txt was not found")
        wheels = offline_dir / "wheels"
        wheels.mkdir(parents=True, exist_ok=True)
        run(
            [sys.executable, "-m", "pip", "download", "--prefer-binary", "-r", project.requirements, "-d", wheels],
            project.root,
        )
    if scope.frontend:
        cache = offline_dir / "npm-cache"
        cache.mkdir(parents=True, exist_ok=True)
        populate_npm_cache(project, cache)
    print(f"[ok] offline dependencies prepared at {offline_dir}")


def populate_npm_cache(project: Project, cache: Path) -> None:
    """Populate npm cache in a temporary install tree, leaving the workspace untouched."""
    with tempfile.TemporaryDirectory(prefix="launcher-npm-") as temporary:
        staging = Path(temporary)
        for name in ("package.json", "package-lock.json", "npm-shrinkwrap.json", ".npmrc"):
            source = project.frontend / name
            if source.is_file():
                shutil.copy2(source, staging / name)
        command = [required_tool("npm"), npm_install_action(project), "--ignore-scripts"]
        run([*command, "--cache", cache, "--prefer-offline"], staging)


def npm_install_action(project: Project) -> str:
    """Use deterministic npm installs when a lockfile is available."""
    return "ci" if (project.frontend / "package-lock.json").is_file() else "install"


def require_files(path: Path, label: str) -> None:
    """Require a non-empty prepared dependency directory."""
    if not path.is_dir() or not any(item.is_file() for item in path.rglob("*")):
        raise LauncherError(f"{label} not found at {path}; run prepare-offline first")
