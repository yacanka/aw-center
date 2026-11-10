#!/usr/bin/env python3
"""Build deterministic release checksums and a dependency SBOM."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path

REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^;\s]+)")
FRONTEND_ROOT = Path("frontend/dist")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    commit = git(root, "rev-parse", "HEAD")
    if not args.allow_dirty and not release_worktree_is_clean(root):
        raise SystemExit("release metadata requires a clean Git worktree")
    files = release_files(root)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": 2,
        "release": args.release,
        "commit": commit,
        "frontend": frontend_metadata(root),
        "files": [file_entry(root, path) for path in files],
    }
    write_json(output / "release-manifest.json", manifest)
    write_json(output / "sbom.cdx.json", build_sbom(root, args.release, commit))
    return 0


def release_files(root: Path) -> list[Path]:
    frontend_dist = root / "frontend" / "dist"
    if frontend_dist.is_symlink():
        raise SystemExit("release input frontend/dist cannot be a symlink")
    if not (frontend_dist / "index.html").is_file():
        raise SystemExit("release metadata requires a built frontend/dist artifact")
    tracked = [root / line for line in git(root, "ls-files").splitlines() if line]
    generated = list(frontend_dist.rglob("*"))
    selected = []
    for path in [*tracked, *generated]:
        if path.is_symlink():
            raise SystemExit(f"release input cannot be a symlink: {path}")
        if not path.exists() or not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise SystemExit(f"release input escaped the repository: {path}")
        relative = path.relative_to(root)
        if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in relative.parts):
            continue
        if path.suffix == ".pyc" or path.name.startswith(".env") and path.name != ".env.example":
            continue
        selected.append(path)
    return sorted(set(selected), key=lambda item: item.relative_to(root).as_posix())


def file_entry(root: Path, path: Path) -> dict[str, int | str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def frontend_metadata(root: Path) -> dict[str, int | str]:
    """Fingerprint the exact reviewed frontend tree embedded by the image build."""

    frontend_input = root / FRONTEND_ROOT
    if frontend_input.is_symlink():
        raise SystemExit("release input frontend/dist cannot be a symlink")
    frontend_dist = frontend_input.resolve()
    if not (frontend_dist / "index.html").is_file():
        raise SystemExit("release metadata requires a built frontend/dist artifact")
    entries = {}
    for path in sorted(frontend_dist.rglob("*")):
        if path.is_symlink():
            raise SystemExit(f"release input cannot be a symlink: {path}")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(frontend_dist):
            raise SystemExit(f"release input escaped frontend/dist: {path}")
        entries[path.relative_to(frontend_dist).as_posix()] = {
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
    return {
        "root": FRONTEND_ROOT.as_posix(),
        "tree_sha256": tree_sha256(entries),
        "files": len(entries),
    }


def tree_sha256(entries: dict) -> str:
    encoded = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_sbom(root: Path, release: str, commit: str) -> dict:
    components = [*python_components(root), *npm_components(root)]
    components.sort(key=lambda item: (item["type"], item["name"], item["version"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, commit + ':' + release)}",
        "version": 1,
        "metadata": {
            "timestamp": git(root, "show", "-s", "--format=%cI", commit),
            "component": {
                "type": "application",
                "name": "aw-center",
                "version": release,
                "properties": [{"name": "git:commit", "value": commit}],
            },
        },
        "components": components,
    }


def release_worktree_is_clean(root: Path) -> bool:
    """Reject source mutations while allowing known generated release evidence."""

    for arguments in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            return False
    untracked = git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
    ).splitlines()
    return all(path == "image-build-metadata.json" for path in untracked)


def python_components(root: Path) -> list[dict[str, str]]:
    components = []
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        match = REQUIREMENT.match(line.strip())
        if not match:
            continue
        name, version = match.groups()
        normalized = name.lower().replace("_", "-")
        components.append(
            {
                "type": "library",
                "name": normalized,
                "version": version,
                "purl": f"pkg:pypi/{normalized}@{version}",
            }
        )
    return components


def npm_components(root: Path) -> list[dict[str, str]]:
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    components = []
    seen = set()
    for package_path, metadata in lock.get("packages", {}).items():
        if not package_path or not package_path.startswith("node_modules/"):
            continue
        name = metadata.get("name") or package_name_from_lock_path(package_path)
        version = metadata.get("version")
        if not isinstance(name, str) or not isinstance(version, str) or (name, version) in seen:
            continue
        seen.add((name, version))
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:npm/{name.replace('@', '%40')}@{version}",
            }
        )
    return components


def package_name_from_lock_path(package_path: str) -> str:
    """Return the package segment after the deepest node_modules boundary."""

    marker = "node_modules/"
    return package_path.rsplit(marker, 1)[-1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise SystemExit("Git metadata is unavailable")
    return completed.stdout.strip()


def write_json(path: Path, payload: dict) -> None:
    try:
        with path.open("x", encoding="utf-8") as destination:
            destination.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        raise SystemExit(f"release evidence already exists: {path}") from None


if __name__ == "__main__":
    raise SystemExit(main())
