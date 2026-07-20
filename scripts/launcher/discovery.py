"""Conservative Django and Vue project discovery."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .model import LauncherError, Project

IGNORED_DIRECTORIES = {".git", ".venv", "node_modules", "dist", "build"}


def discover_project(root: Path | None = None) -> Project:
    """Discover one Django backend and one Vue frontend below a project root."""
    project_root = resolve_root(root)
    manage_py = choose_file(project_root, "manage.py", preferred=("manage.py", "backend/manage.py"))
    package_json = choose_vue_manifest(project_root)
    requirements = choose_requirements(project_root, manage_py.parent)
    return Project(project_root, manage_py, package_json, requirements)


def resolve_root(explicit_root: Path | None) -> Path:
    """Resolve an explicit root or find the nearest plausible repository root."""
    if explicit_root:
        resolved = explicit_root.expanduser().resolve()
        if not resolved.is_dir():
            raise LauncherError(f"project root does not exist: {resolved}")
        return resolved

    starts = (Path.cwd().resolve(), Path(__file__).resolve().parents[2])
    for start in starts:
        for candidate in (start, *start.parents):
            if has_project_markers(candidate):
                return candidate
    raise LauncherError("project root not found; pass --root <directory>")


def has_project_markers(path: Path) -> bool:
    """Return whether a directory looks like a Django and Node repository."""
    django = (path / "manage.py").is_file() or (path / "backend/manage.py").is_file()
    node = (path / "package.json").is_file() or (path / "frontend/package.json").is_file()
    return django and node


def choose_file(root: Path, name: str, *, preferred: tuple[str, ...]) -> Path:
    """Select a preferred file and reject ambiguous recursive matches."""
    for relative in preferred:
        candidate = root / relative
        if candidate.is_file():
            return candidate

    matches = bounded_matches(root, name)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LauncherError(f"{name} was not found under {root}")
    raise LauncherError(f"multiple {name} files found; select the project with --root")


def choose_vue_manifest(root: Path) -> Path:
    """Select the nearest package manifest that declares Vue."""
    preferred = (root / "frontend/package.json", root / "package.json")
    candidates = [*preferred, *bounded_matches(root, "package.json")]
    unique = list(dict.fromkeys(path for path in candidates if path.is_file()))
    vue_manifests = [path for path in unique if manifest_uses_vue(path)]
    if not vue_manifests:
        raise LauncherError(f"Vue package.json was not found under {root}")
    return vue_manifests[0]


def manifest_uses_vue(path: Path) -> bool:
    """Return whether a package manifest declares Vue or a Vite Vue plugin."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError(f"invalid package manifest {path}: {error}") from error
    packages = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    return "vue" in packages or "@vitejs/plugin-vue" in packages


def choose_requirements(root: Path, backend: Path) -> Path | None:
    """Return the conventional requirements file when present."""
    candidates = (root / "requirements.txt", backend / "requirements.txt")
    return next((path for path in candidates if path.is_file()), None)


def bounded_matches(root: Path, name: str) -> list[Path]:
    """Find matching files at a small depth while ignoring generated trees."""
    matches = []
    for path in root.glob(f"**/{name}"):
        relative = path.relative_to(root)
        if len(relative.parts) > 4:
            continue
        if set(relative.parts).intersection(IGNORED_DIRECTORIES):
            continue
        matches.append(path)
    return sorted(matches)


def infer_wsgi_application(project: Project) -> str:
    """Infer the WSGI import path from manage.py's settings module."""
    content = project.manage_py.read_text(encoding="utf-8")
    match = re.search(r"DJANGO_SETTINGS_MODULE['\"],\s*['\"]([^'\"]+)", content)
    if not match:
        raise LauncherError("could not infer DJANGO_SETTINGS_MODULE from manage.py")
    settings_module = match.group(1)
    package = settings_module.removesuffix(".settings")
    return f"{package}.wsgi:application"
