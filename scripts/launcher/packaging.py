"""Deterministic, secret-conscious ZIP packaging workflows."""

from __future__ import annotations

import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from .dependencies import require_files
from .model import LauncherError, Project, Scope

EXCLUDED_NAMES = {".env", ".env.local", ".DS_Store", "db.sqlite3"}
EXCLUDED_PARTS = {".git", ".venv", ".runtime", "node_modules", "dist", "media", "staticfiles"}
EXCLUDED_SUFFIXES = {
    ".db",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".sqlite",
    ".sqlite3",
}


def package_offline(
    project: Project,
    scope: Scope,
    offline_dir: Path,
    output: Path,
    *,
    include_packages: bool,
) -> None:
    """Package tracked source and prepared dependencies for offline transfer."""
    scope.require_any()
    source_files = tracked_source_files(project, scope)
    dependencies = offline_dependency_entries(scope, offline_dir, include_packages)
    entries = [(path, path.relative_to(project.root)) for path in source_files]
    write_zip(output, entries + dependencies)
    print(f"[ok] offline package created: {output}")


def offline_dependency_entries(
    scope: Scope, offline_dir: Path, include_packages: bool
) -> list[tuple[Path, Path]]:
    """Return prepared dependency files selected for an offline ZIP."""
    dependencies: list[tuple[Path, Path]] = []
    if not include_packages:
        return dependencies
    if include_packages and scope.backend:
        wheels = offline_dir / "wheels"
        require_files(wheels, "offline Python wheels")
        dependencies.extend(mapped_tree(wheels, Path("offline/wheels")))
    if include_packages and scope.frontend:
        cache = offline_dir / "npm-cache"
        require_files(cache, "offline npm cache")
        dependencies.extend(mapped_tree(cache, Path("offline/npm-cache")))
    return dependencies


def package_changes(project: Project, output: Path | None) -> Path | None:
    """Package non-deleted tracked and untracked Git changes."""
    changed = git_paths(project, ["diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"])
    untracked = git_paths(project, ["ls-files", "--others", "--exclude-standard"])
    paths = sorted(set(changed + untracked))
    files = [project.root / path for path in paths if packageable(project.root / path)]
    if not files:
        print("[ok] no packageable Git changes found")
        return None
    target = output or default_changes_zip(project.root)
    write_zip(target, [(path, path.relative_to(project.root)) for path in files])
    print(f"[ok] change package created: {target}")
    return target


def tracked_source_files(project: Project, scope: Scope) -> list[Path]:
    """Return packageable Git-tracked source files."""
    relative_paths = git_paths(project, ["ls-files"])
    files = [project.root / relative for relative in relative_paths]
    launcher_files = [project.root / "launcher.py", project.root / "scripts/launcher"]
    for path in launcher_files:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
    return sorted(set(path for path in files if packageable(path) and in_scope(project, scope, path)))


def in_scope(project: Project, scope: Scope, path: Path) -> bool:
    """Exclude a skipped application side while retaining shared root files."""
    resolved = path.resolve()
    if resolved.is_relative_to(project.backend.resolve()):
        return scope.backend
    if resolved.is_relative_to(project.frontend.resolve()):
        return scope.frontend
    return True


def git_paths(project: Project, arguments: list[str]) -> list[Path]:
    """Read repository-relative paths from one non-mutating Git command."""
    completed = subprocess.run(
        ["git", "-C", str(project.root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise LauncherError("Git repository metadata is required for safe packaging")
    return [Path(line) for line in completed.stdout.splitlines() if line]


def packageable(path: Path) -> bool:
    """Reject generated artifacts and common secret-bearing file types."""
    if not path.is_file():
        return False
    unsafe_env = path.name.startswith(".env") and not path.name.endswith((".example", ".sample"))
    if unsafe_env or path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return not set(path.parts).intersection(EXCLUDED_PARTS)


def mapped_tree(source: Path, destination: Path) -> list[tuple[Path, Path]]:
    """Map files below a dependency directory into a stable archive path."""
    return [
        (path, destination / path.relative_to(source))
        for path in source.rglob("*")
        if path.is_file()
    ]


def write_zip(output: Path, entries: list[tuple[Path, Path]]) -> None:
    """Write unique files to a ZIP using deterministic path ordering."""
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    unique = {archive.as_posix(): source for source, archive in entries if source.resolve() != output}
    if not unique:
        raise LauncherError("no files were selected for packaging")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, source in sorted(unique.items()):
            archive.write(source, archive_name)


def default_changes_zip(root: Path) -> Path:
    """Return a timestamped change-package path below the project root."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return root / f"git-changes-{timestamp}.zip"
