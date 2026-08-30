#!/usr/bin/env python3
"""Verify that a built image contains the exact reviewed frontend artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_METADATA_BYTES = 64 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-metadata", type=Path, required=True)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--expected-dist", type=Path, required=True)
    parser.add_argument("--image-dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metadata = read_json_object(args.image_metadata, "BuildKit metadata")
    manifest = read_json_object(args.release_manifest, "release manifest")
    image_digest = resolved_image_digest(metadata)
    expected = tree_entries(args.expected_dist)
    release, commit = verify_manifest_frontend(manifest, expected)
    actual = tree_entries(args.image_dist)
    if expected != actual:
        raise SystemExit("image frontend artifact does not match reviewed frontend/dist")
    payload = {
        "schema": 2,
        "release": release,
        "commit": commit,
        "release_manifest_sha256": file_sha256(args.release_manifest),
        "image_digest": image_digest,
        "frontend_tree_sha256": tree_digest(expected),
        "frontend_files": len(expected),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, payload)
    return 0


def read_json_object(path: Path, label: str) -> dict:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_METADATA_BYTES
    ):
        raise SystemExit(f"{label} must be a regular file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SystemExit(f"{label} is not valid JSON") from None
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must contain a JSON object")
    return payload


def verify_manifest_frontend(manifest: dict, expected: dict) -> tuple[str, str]:
    """Bind the reviewed dist tree to the source manifest before inspecting the image."""

    if manifest.get("schema") != 2:
        raise SystemExit("release manifest schema is unsupported")
    release = manifest.get("release")
    commit = manifest.get("commit")
    frontend = manifest.get("frontend")
    files = manifest.get("files")
    if not isinstance(release, str) or not release:
        raise SystemExit("release manifest has no release identifier")
    if not isinstance(commit, str) or not commit:
        raise SystemExit("release manifest has no commit identifier")
    if not isinstance(frontend, dict) or not isinstance(files, list):
        raise SystemExit("release manifest has no frontend contract")
    if frontend.get("root") != "frontend/dist":
        raise SystemExit("release manifest frontend root is invalid")

    manifest_entries = {}
    prefix = "frontend/dist/"
    for entry in files:
        if not isinstance(entry, dict):
            raise SystemExit("release manifest contains an invalid file entry")
        path = entry.get("path")
        if not isinstance(path, str) or not path.startswith(prefix):
            continue
        relative = path.removeprefix(prefix)
        if not relative or relative in manifest_entries:
            raise SystemExit("release manifest contains an invalid frontend path")
        manifest_entries[relative] = {
            "sha256": entry.get("sha256"),
            "size": entry.get("size"),
        }

    expected_digest = tree_digest(expected)
    if manifest_entries != expected:
        raise SystemExit("reviewed frontend/dist does not match the release manifest")
    if frontend.get("tree_sha256") != expected_digest:
        raise SystemExit("release manifest frontend tree digest is invalid")
    if frontend.get("files") != len(expected):
        raise SystemExit("release manifest frontend file count is invalid")
    return release, commit


def resolved_image_digest(metadata: dict) -> str:
    digest = metadata.get("containerimage.digest")
    if not isinstance(digest, str) or not IMAGE_DIGEST.fullmatch(digest):
        raise SystemExit("BuildKit metadata has no resolved immutable image digest")
    return digest


def tree_entries(root: Path) -> dict[str, dict[str, int | str]]:
    root = root.expanduser()
    if root.is_symlink():
        raise SystemExit(f"frontend artifact root cannot be a symlink: {root}")
    root = root.resolve()
    if not (root / "index.html").is_file():
        raise SystemExit(f"frontend artifact is incomplete: {root}")
    entries = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SystemExit(f"frontend artifact cannot contain a symlink: {path}")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise SystemExit(f"frontend artifact escaped its root: {path}")
        entries[path.relative_to(root).as_posix()] = {
            "sha256": file_sha256(path),
            "size": path.stat().st_size,
        }
    return entries


def tree_digest(entries: dict) -> str:
    encoded = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    """Create immutable release evidence without replacing an earlier result."""

    try:
        with path.open("x", encoding="utf-8") as destination:
            destination.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        raise SystemExit(f"release evidence already exists: {path}") from None


if __name__ == "__main__":
    raise SystemExit(main())
