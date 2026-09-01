"""Platform-bound checksum manifest for offline dependency bundles."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

from .model import LauncherError, Project, Scope
from .process import required_tool

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1


def write_offline_manifest(project: Project, scope: Scope, offline_dir: Path) -> Path:
    """Record target/toolchain/lock metadata and every prepared artifact digest."""

    manifest_path = offline_dir / MANIFEST_NAME
    manifest = {
        "format_version": MANIFEST_VERSION,
        "commit": git_commit(project.root),
        "target": target_metadata(),
        "toolchain": toolchain_metadata(scope),
        "locks": lock_metadata(project, scope),
        "artifacts": artifact_metadata(offline_dir),
    }
    offline_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def verify_offline_manifest(project: Project, scope: Scope, offline_dir: Path) -> dict:
    """Fail closed when a prepared bundle is stale, cross-platform, or modified."""

    path = offline_dir / MANIFEST_NAME
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError("offline dependency manifest is missing or invalid") from error
    if manifest.get("format_version") != MANIFEST_VERSION:
        raise LauncherError("offline dependency manifest version is unsupported")
    if manifest.get("target") != target_metadata():
        raise LauncherError("offline dependencies target a different OS, architecture, or Python")
    if manifest.get("locks") != lock_metadata(project, scope):
        raise LauncherError("offline dependencies do not match the current lock files")
    expected = manifest.get("artifacts")
    if not isinstance(expected, list) or expected != artifact_metadata(offline_dir):
        raise LauncherError("offline dependency checksum verification failed")
    return manifest


def target_metadata() -> dict[str, str]:
    return {
        "implementation": sys.implementation.name,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "system": platform.system().lower(),
        "machine": platform.machine().lower(),
    }


def toolchain_metadata(scope: Scope) -> dict[str, str]:
    metadata = {
        "python": platform.python_version(),
        "pip": importlib.metadata.version("pip"),
    }
    if scope.frontend:
        metadata["node"] = command_version("node")
        metadata["npm"] = command_version("npm")
    return metadata


def lock_metadata(project: Project, scope: Scope) -> dict[str, str]:
    locks = {}
    if scope.backend:
        if not project.requirements or not project.requirements.is_file():
            raise LauncherError("requirements lock is unavailable")
        locks[project.requirements.name] = file_sha256(project.requirements)
    if scope.frontend:
        lock = project.frontend / "package-lock.json"
        if not lock.is_file():
            raise LauncherError("frontend package-lock.json is required for offline packaging")
        locks[lock.relative_to(project.root).as_posix()] = file_sha256(lock)
    return locks


def artifact_metadata(offline_dir: Path) -> list[dict[str, int | str]]:
    artifacts = []
    for path in sorted(offline_dir.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        if path.is_symlink():
            raise LauncherError("offline dependencies cannot contain symbolic links")
        artifacts.append(
            {
                "path": path.relative_to(offline_dir).as_posix(),
                "sha256": file_sha256(path),
                "size": path.stat().st_size,
            }
        )
    return artifacts


def ensure_wheels_only(wheels: Path) -> None:
    """Reject source distributions and non-wheel Python dependency artifacts."""

    invalid = [path.name for path in wheels.iterdir() if path.is_file() and path.suffix != ".whl"]
    if invalid:
        raise LauncherError(f"offline Python dependencies contain non-wheel artifacts: {invalid[0]}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise LauncherError("Git commit metadata is required for offline packaging")
    return completed.stdout.strip()


def command_version(command: str) -> str:
    executable = required_tool(command)
    completed = subprocess.run(
        [executable, "--version"], check=False, capture_output=True, text=True
    )
    if completed.returncode:
        raise LauncherError(f"{command} version could not be determined")
    return completed.stdout.strip()
