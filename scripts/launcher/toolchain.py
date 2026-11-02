"""User-scoped, verified Windows toolchains with process-local environment."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tarfile
import zipfile
from pathlib import Path

from .installation_sources import Artifact, SourceSettings, _digest, _no_symlink, _safe_member, _verify as verify_artifact, fetch_artifact, load_catalog, safe_extract
from .installation_state import private_directory
from .model import LauncherError

RECEIPT = ".awcenter-tool.json"
MANAGED_RUNTIME_ENVIRONMENT = {
    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    "PYTHONHOME": "", "PYTHONPATH": "", "PYTHONSTARTUP": "", "PYTHONUSERBASE": "",
    "NODE_OPTIONS": "", "NODE_TLS_REJECT_UNAUTHORIZED": "1",
}


def _directory(home: Path, artifact: Artifact) -> Path:
    return home / "runtimes" / f"{artifact.name}-{artifact.version}"


def _inventory(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(directory.rglob("*")):
        _no_symlink(path)
        if path.is_file() and path.name != RECEIPT:
            result[path.relative_to(directory).as_posix()] = _digest(path)
    return result


def _check_version(executable: Path, version: str, *, node: Path | None = None) -> None:
    command = [str(executable), "--version"] if node is None else [str(node), str(executable), "--version"]
    if executable.name == "python.exe":
        command[1:1] = ["-I", "-S", "-B", "-X", "utf8", "-X", "frozen_modules=on"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30, env={**os.environ, **MANAGED_RUNTIME_ENVIRONMENT})
    except (OSError, subprocess.TimeoutExpired):
        raise LauncherError("managed runtime could not be validated") from None
    rendered = completed.stdout.strip()
    expected = "Python " + version if executable.name == "python.exe" else version
    if completed.returncode or rendered.removeprefix("v") != expected:
        raise LauncherError("managed runtime version does not match the reviewed catalog")


def _npm_wrapper_files(node: Path, target: Path) -> dict[str, bytes]:
    relative_node = os.path.relpath(node, target / "bin").replace("/", "\\")
    return {
        f"bin/{command}.cmd": f'@echo off\r\nsetlocal DisableDelayedExpansion\r\n"%~dp0{relative_node}" "%~dp0..\\package\\bin\\{command}-cli.js" %*\r\n'.encode("ascii")
        for command in ("npm", "npx")
    }


def _npm_wrappers(directory: Path, node: Path, target: Path) -> None:
    (directory / "bin").mkdir()
    for relative, content in _npm_wrapper_files(node, target).items():
        (directory / relative).write_bytes(content)


def _trusted_inventory(home: Path, artifact: Artifact, catalog: dict[str, Artifact]) -> dict[str, str]:
    """Derive expected hashes from the catalog-pinned archive, never receipts."""
    archive = home / "cache/runtimes" / artifact.filename
    verify_artifact(archive, artifact)
    result = {}
    if artifact.archive == "zip":
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                relative = str(_safe_member(member.filename))
                if member.is_dir():
                    continue
                with source.open(member) as stream:
                    result[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    else:
        with tarfile.open(archive, "r:gz") as source:
            for member in source:
                relative = str(_safe_member(member.name))
                if member.isdir():
                    continue
                if not member.isfile():
                    raise LauncherError("reviewed runtime archive contains unsupported entries")
                with source.extractfile(member) as stream:
                    result[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    if artifact.name == "npm":
        node = _directory(home, catalog["node"]) / catalog["node"].executable
        for relative, content in _npm_wrapper_files(node, _directory(home, artifact)).items():
            result[relative] = hashlib.sha256(content).hexdigest()
    return result


def _install(home: Path, artifact: Artifact, archive: Path, *, node: Path | None = None) -> Path:
    target = _directory(home, artifact)
    _no_symlink(target)
    with tempfile.TemporaryDirectory(prefix=".tool-", dir=home / "runtimes") as temporary:
        stage = Path(temporary) / "content"
        safe_extract(archive, stage, artifact.archive)
        executable = stage / artifact.executable
        if not executable.is_file():
            raise LauncherError("reviewed runtime executable is missing from its archive")
        if artifact.name == "npm":
            _npm_wrappers(stage, node, target)
        expected = _inventory(stage)
        if target.exists():
            # CMD may already have expanded this pinned Python before Python was
            # available. Authenticate its files against the freshly verified archive.
            if _inventory(target) != expected:
                raise LauncherError(f"managed {artifact.name} files differ from the reviewed archive")
        else:
            shutil.move(str(stage), str(target))
        _check_version(target / artifact.executable, artifact.version, node=node)
        receipt = {"name": artifact.name, "version": artifact.version, "sha256": artifact.sha256, "files": expected}
        receipt_path = target / RECEIPT
        _no_symlink(receipt_path)
        contents = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
        if not receipt_path.exists() or receipt_path.read_text(encoding="utf-8") != contents:
            receipt_path.write_text(contents, encoding="utf-8")
    return target / artifact.executable


def ensure_toolchain(home: Path, settings: SourceSettings) -> dict[str, str]:
    """Install reviewed native artifacts; return environment overrides only.

    Hosts do not receive global PATH, registry or dependency-lock modifications.
    The caller owns when to apply the returned process-local environment.
    """
    home = Path(home)
    _no_symlink(home)
    catalog = load_catalog()
    for directory in (home, home / "cache", home / "cache" / "runtimes", home / "runtimes"):
        private_directory(directory)
    paths = {}
    for name in ("python", "node", "npm"):
        artifact = catalog[name]
        archive = fetch_artifact(artifact, home / "cache" / "runtimes", settings)
        paths[name] = _install(home, artifact, archive, node=paths.get("node") if name == "npm" else None)
    return _environment(home, catalog)


def _environment(home: Path, catalog: dict[str, Artifact]) -> dict[str, str]:
    paths = {name: _directory(home, artifact) / artifact.executable for name, artifact in catalog.items()}
    directories = [paths["python"].parent, paths["python"].parent / "Scripts", paths["node"].parent, _directory(home, catalog["npm"]) / "bin"]
    # npm must precede the npm bundled by Node, preserving the repository pin.
    directories.insert(0, directories.pop())
    return {**MANAGED_RUNTIME_ENVIRONMENT, "PATH": os.pathsep.join([*(str(path) for path in directories), os.environ.get("PATH", "")]), "AWCENTER_MANAGED_PYTHON": str(paths["python"]), "AWCENTER_MANAGED_NODE": str(paths["node"]), "AWCENTER_MANAGED_NPM_CLI": str(paths["npm"])}


def inspect_toolchain(home: Path) -> list[dict]:
    """Inspect receipts and all installed artifact files without writes or execution."""
    checks = []
    catalog = load_catalog()
    for name, artifact in catalog.items():
        target = _directory(Path(home), artifact)
        check = {"name": name, "status": "missing", "detail": f"managed {name} {artifact.version} is missing"}
        if not target.exists():
            checks.append(check)
            continue
        try:
            _no_symlink(target)
            _no_symlink(target / RECEIPT)
            receipt = json.loads((target / RECEIPT).read_text(encoding="utf-8"))
            if receipt["name"] != name or receipt["version"] != artifact.version or receipt["sha256"] != artifact.sha256:
                raise ValueError("pin mismatch")
            if _inventory(target) != _trusted_inventory(Path(home), artifact, catalog):
                raise ValueError("modified runtime")
            check.update(status="ready", detail=f"managed {name} {artifact.version} verified")
        except (OSError, ValueError, KeyError, TypeError, LauncherError, tarfile.TarError, zipfile.BadZipFile):
            check.update(status="invalid", detail=f"managed {name} integrity check failed; provision requires reviewed files")
        checks.append(check)
    return checks


def toolchain_environment(home: Path) -> dict[str, str]:
    """Return existing verified runtimes without retrieval, extraction or writes."""
    if any(check["status"] != "ready" for check in inspect_toolchain(home)):
        raise LauncherError("managed toolchain is incomplete or invalid; run provision")
    return _environment(Path(home), load_catalog())
