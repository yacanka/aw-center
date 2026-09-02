#!/usr/bin/env python3
"""Fail-closed validation for the operator-owned Compose environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import unquote, urlsplit

RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
REDIS_PASSWORD = re.compile(r"^[A-Za-z0-9._~-]{24,128}$")
DOORS_RUNNER_TOKEN = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
PLACEHOLDERS = {
    "change-me",
    "replace-password",
    "replace-with-a-long-random-production-secret",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--image-verification", type=Path, required=True)
    args = parser.parse_args()
    values = read_env_file(args.env_file) if args.env_file else {}
    values.update(os.environ)
    errors = validate(values)
    errors.extend(
        validate_release_evidence(
            values,
            args.release_manifest,
            args.image_verification,
        )
    )
    if errors:
        raise SystemExit("deployment environment is invalid: " + ", ".join(errors))
    return 0


def validate(values) -> list[str]:
    errors = []
    release = str(values.get("AWCENTER_RELEASE", ""))
    image = str(values.get("AWCENTER_IMAGE", ""))
    host = str(values.get("AWCENTER_HOST", "")).strip().lower()
    secret = str(values.get("SECRET_KEY", ""))
    database_url = str(values.get("DATABASE_URL", ""))
    postgres_password = str(values.get("POSTGRES_PASSWORD", ""))
    redis_password = str(values.get("REDIS_PASSWORD", ""))

    if not RELEASE.fullmatch(release) or _placeholder(release):
        errors.append("AWCENTER_RELEASE")
    if not IMAGE.fullmatch(image):
        errors.append("AWCENTER_IMAGE")
    if (
        not HOST.fullmatch(host)
        or _reserved_host(host)
    ):
        errors.append("AWCENTER_HOST")
    if len(secret) < 50 or _placeholder(secret):
        errors.append("SECRET_KEY")
    database = _database_config(database_url)
    database_password = None
    if database is None:
        errors.append("DATABASE_URL")
    else:
        (
            database_host,
            database_port,
            database_password,
            database_user,
            database_name,
        ) = database
        if (
            database_host != "database"
            or database_port not in {None, 5432}
            or database_user != str(values.get("POSTGRES_USER", "") or "awcenter")
            or database_name != str(values.get("POSTGRES_DB", "") or "awcenter")
        ):
            errors.append("DATABASE_URL_TOPOLOGY")
    if not postgres_password or _placeholder(postgres_password):
        errors.append("POSTGRES_PASSWORD")
    elif database_password is not None and postgres_password != database_password:
        errors.append("POSTGRES_PASSWORD_MISMATCH")
    if not REDIS_PASSWORD.fullmatch(redis_password) or _placeholder(redis_password):
        errors.append("REDIS_PASSWORD")
    errors.extend(_validate_runtime_paths(values))
    errors.extend(_validate_doors_runner(values))
    return errors


def validate_release_evidence(
    values: dict[str, str],
    manifest_path: Path,
    verification_path: Path,
) -> list[str]:
    """Verify that operator env, source manifest, frontend tree, and image digest agree."""

    manifest = _read_json(manifest_path)
    verification = _read_json(verification_path)
    if manifest is None:
        return ["RELEASE_MANIFEST"]
    if verification is None:
        return ["IMAGE_VERIFICATION"]

    errors = []
    release = str(values.get("AWCENTER_RELEASE", ""))
    image = str(values.get("AWCENTER_IMAGE", ""))
    image_digest = image.rpartition("@sha256:")[2]
    frontend = manifest.get("frontend")
    if manifest.get("schema") != 2:
        errors.append("RELEASE_MANIFEST_SCHEMA")
    if manifest.get("release") != release:
        errors.append("RELEASE_MISMATCH")
    if not isinstance(frontend, dict):
        errors.append("RELEASE_FRONTEND")
        frontend = {}
    elif (
        frontend.get("root") != "frontend/dist"
        or not SHA256.fullmatch(str(frontend.get("tree_sha256", "")))
        or not isinstance(frontend.get("files"), int)
        or frontend.get("files", 0) < 1
    ):
        errors.append("RELEASE_FRONTEND")
    if not COMMIT.fullmatch(str(manifest.get("commit", ""))):
        errors.append("RELEASE_COMMIT")
    if verification.get("schema") != 2:
        errors.append("IMAGE_VERIFICATION_SCHEMA")
    if verification.get("release") != manifest.get("release"):
        errors.append("IMAGE_RELEASE_MISMATCH")
    if verification.get("commit") != manifest.get("commit"):
        errors.append("IMAGE_COMMIT_MISMATCH")
    if verification.get("release_manifest_sha256") != _file_sha256(manifest_path):
        errors.append("RELEASE_MANIFEST_DIGEST_MISMATCH")
    if verification.get("image_digest") != f"sha256:{image_digest}":
        errors.append("IMAGE_DIGEST_MISMATCH")
    if verification.get("frontend_tree_sha256") != frontend.get("tree_sha256"):
        errors.append("FRONTEND_TREE_MISMATCH")
    if verification.get("frontend_files") != frontend.get("files"):
        errors.append("FRONTEND_FILE_COUNT_MISMATCH")
    return errors


def _validate_runtime_paths(values: dict[str, str]) -> list[str]:
    errors = []
    certificate = _regular_file(values.get("TLS_CERTIFICATE_FILE"))
    private_key = _regular_file(values.get("TLS_PRIVATE_KEY_FILE"))
    model_directory = _directory(values.get("MODEL_DIRECTORY"))
    if certificate is None:
        errors.append("TLS_CERTIFICATE_FILE")
    if private_key is None:
        errors.append("TLS_PRIVATE_KEY_FILE")
    elif stat.S_IMODE(private_key.stat().st_mode) & 0o077:
        errors.append("TLS_PRIVATE_KEY_PERMISSIONS")
    if certificate is not None and private_key is not None and certificate == private_key:
        errors.append("TLS_KEY_CERTIFICATE_COLLISION")
    if model_directory is None:
        errors.append("MODEL_DIRECTORY")
    return errors


def _validate_doors_runner(values: dict[str, str]) -> list[str]:
    """Require a strong shared secret only when the local runner is enabled."""

    if not _truthy(values.get("DOORS_ENABLED")):
        return []
    token = str(values.get("DOORS_RUNNER_TOKEN", ""))
    return [] if DOORS_RUNNER_TOKEN.fullmatch(token) else ["DOORS_RUNNER_TOKEN"]


def _read_json(path: Path) -> dict | None:
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_EVIDENCE_BYTES
        ):
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(value) -> Path | None:
    if not value:
        return None
    supplied_path = Path(str(value)).expanduser()
    if supplied_path.is_symlink():
        return None
    path = supplied_path.resolve()
    return (
        path
        if path.is_file() and path.stat().st_size > 0
        else None
    )


def _directory(value) -> Path | None:
    if not value:
        return None
    supplied_path = Path(str(value)).expanduser()
    if supplied_path.is_symlink():
        return None
    path = supplied_path.resolve()
    return path if path.is_dir() else None


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for raw_line in path.expanduser().read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in PLACEHOLDERS or normalized.startswith("replace-")


def _reserved_host(host: str) -> bool:
    return (
        host == "localhost"
        or host == "example.com"
        or host.endswith(".example.com")
        or host.endswith(".invalid")
    )


def _database_config(
    database_url: str,
) -> tuple[str, int | None, str, str, str] | None:
    try:
        parsed = urlsplit(database_url)
        if parsed.scheme not in {"postgres", "postgresql"}:
            return None
        if not parsed.hostname or not parsed.username or not parsed.password:
            return None
        database_name = unquote(parsed.path.removeprefix("/"))
        if not database_name or "/" in database_name:
            return None
        password = unquote(parsed.password)
        if _placeholder(password):
            return None
        return (
            parsed.hostname.lower(),
            parsed.port,
            password,
            unquote(parsed.username),
            database_name,
        )
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
