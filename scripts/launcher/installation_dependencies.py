"""Acquire locked packages before installing; fallback is limited to availability."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .certificates import package_trust_environment
from .installation_sources import SourceSettings, acquisition_urls
from .model import LauncherError, Project, Scope
from .offline_manifest import verify_offline_manifest
from .process import controlled_run, environment


def availability_failure(output: str) -> bool:
    """Package managers have no common typed network error protocol; fail closed.

    Only their explicit transport/not-found signatures permit source fallback.
    Unknown failures are installation failures, even if that requires a manual retry.
    """
    text = output.casefold()
    fatal = ("certificate", "sslerror", "eintegrity", "hash mismatch", "failed building wheel",
             "subprocess-exited-with-error", "eresolve", "no space", "access is denied", "permission denied")
    if any(value in text for value in fatal):
        return False
    return any(value in text for value in (
        "newconnectionerror", "connection refused", "connection reset", "readtimeouterror",
        "connecttimeouterror", "nameresolutionerror", "enotfound", "eai_again", "econnrefused",
        "econnreset", "err_socket_timeout", "etimedout", "http error 404", "e404",
        "503 service unavailable", "502 bad gateway", "504 gateway timeout",
    ))


def capture(command: list, project: Project, overrides: dict | None = None, *, timeout=1800):
    """Do not echo package-manager diagnostics, which may contain proxy credentials."""
    values = environment(overrides)
    values = {key: value for key, value in values.items()
              if not key.upper().startswith(("PIP_", "NPM_CONFIG_"))}
    values.update({"PIP_CONFIG_FILE": os.devnull, "PIP_NO_INPUT": "1",
                   "PIP_DEFAULT_TIMEOUT": "10", "PIP_RETRIES": "1",
                   "NPM_CONFIG_USERCONFIG": os.devnull, "NPM_CONFIG_GLOBALCONFIG": os.devnull,
                   "NODE_TLS_REJECT_UNAUTHORIZED": "1", "NPM_CONFIG_STRICT_SSL": "true",
                   "NPM_CONFIG_FETCH_RETRIES": "1", "NPM_CONFIG_FETCH_TIMEOUT": "15000"})
    if overrides:
        values.update(overrides)
    try:
        return controlled_run([str(part) for part in command], cwd=project.root, env=values,
                              capture_output=True, text=True, timeout=timeout, check=False,
                              safe_boundary=any(str(part) == "migrate" for part in command))
    except subprocess.TimeoutExpired:
        raise LauncherError("Paket işlemi süre sınırını aştı; kurulum yeniden çalıştırılabilir.") from None


def _succeeded(result, stage: str) -> None:
    if result.returncode:
        raise LauncherError(f"{stage} başarısız; kurulum durduruldu. Kaynak ve araç durumunu doctor ile kontrol edin.")


def _offline_candidates(settings: SourceSettings):
    roots = []
    if settings.repository and not str(settings.repository).startswith("https://"):
        roots.append(Path(settings.repository))
    if settings.offline_dir:
        roots.append(Path(settings.offline_dir))
    for root in roots:
        for directory in (root / "dependencies", root):
            if (directory / "manifest.json").is_file():
                yield directory


def _offline_dependencies(project: Project, settings: SourceSettings) -> Path | None:
    for candidate in _offline_candidates(settings):
        verify_offline_manifest(project, Scope(), candidate)
        return candidate
    return None


def _ensure_venv(project: Project, tool_env: dict, *, expected_python: Path | None = None) -> None:
    if not project.python.is_file():
        if project.venv.exists():
            raise LauncherError("Mevcut .venv eksik; otomatik silinmedi. Ayrı temiz kaynak dizini kullanın.")
        _succeeded(capture([tool_env["AWCENTER_MANAGED_PYTHON"], "-m", "venv", project.venv], project,
                           tool_env), "Virtual environment oluşturma")
    result = capture([project.python, "-c", "import sys,struct; print(sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8)"], project, tool_env)
    if result.returncode or result.stdout.strip() != "True":
        raise LauncherError("Mevcut .venv CPython 3.11 x64 ile oluşturulmalı; otomatik değiştirilmedi.")
    if expected_python is not None:
        base = capture([project.python, '-I', '-c',
                        'import sys; print(getattr(sys, "_base_executable", sys.executable))'], project, tool_env)
        if (base.returncode or not base.stdout.strip() or
                Path(base.stdout.strip()).resolve() != Path(expected_python).resolve()):
            raise LauncherError('Mevcut .venv farklı bir Python kullanıyor; otomatik değiştirilmedi. Ayrı temiz kaynak dizini kullanın.')


def _python_packages(project: Project, settings: SourceSettings, tool_env: dict, stage: Path) -> None:
    if not project.requirements:
        raise LauncherError("Python requirements lock dosyası bulunamadı.")
    wheelhouse = stage / "wheels"
    indexes = acquisition_urls(settings, "https://pypi.org/simple", settings.python_index_url)
    for index in indexes:
        wheelhouse.mkdir(exist_ok=True)
        result = capture([project.python, "-m", "pip", "wheel", "--wheel-dir", wheelhouse,
                          "--index-url", index, "-r", project.requirements], project, tool_env)
        if not result.returncode:
            break
        if not availability_failure(result.stdout + result.stderr):
            _succeeded(result, "Python paket edinimi")
    else:
        offline = _offline_dependencies(project, settings)
        if not offline:
            raise LauncherError("Kilitli Python paketleri internet, seçilen depo veya offline dizinde bulunamadı.")
        wheelhouse = offline / "wheels"
    _succeeded(capture([project.python, "-m", "pip", "install", "--no-index", "--find-links", wheelhouse,
                       "-r", project.requirements], project, tool_env), "Python paket kurulumu")
    _succeeded(capture([project.python, "-m", "pip", "check"], project, tool_env), "Python bağımlılık doğrulaması")


def _npm_command(tool_env: dict) -> list[str]:
    if tool_env.get("AWCENTER_MANAGED_NODE") and tool_env.get("AWCENTER_MANAGED_NPM_CLI"):
        return [tool_env["AWCENTER_MANAGED_NODE"], tool_env["AWCENTER_MANAGED_NPM_CLI"]]
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm", path=tool_env.get("PATH"))
    if not npm:
        raise LauncherError("Doğrulanmış npm bulunamadı.")
    return [npm]


def _frontend_packages(project: Project, settings: SourceSettings, tool_env: dict, stage: Path) -> None:
    npm = _npm_command(tool_env)
    tree, cache = stage / "npm-source", stage / "npm-cache"
    tree.mkdir()
    for name in ("package.json", "package-lock.json"):
        source = project.frontend / name
        if not source.is_file():
            raise LauncherError("Frontend lock dosyası eksik.")
        shutil.copyfile(source, tree / name)
    registries = acquisition_urls(settings, "https://registry.npmjs.org", settings.npm_registry_url)
    for registry in registries:
        result = capture([*npm, "ci", "--prefix", tree, "--ignore-scripts", "--cache", cache,
                          "--registry", registry, "--replace-registry-host=npmjs", "--no-audit", "--no-fund"],
                         project, tool_env)
        if not result.returncode:
            break
        if not availability_failure(result.stdout + result.stderr):
            _succeeded(result, "npm paket edinimi")
    else:
        offline = _offline_dependencies(project, settings)
        if not offline:
            raise LauncherError("Kilitli npm paketleri internet, seçilen depo veya offline dizinde bulunamadı.")
        cache = stage / "offline-npm-cache"
        shutil.copytree(offline / "npm-cache", cache)
    _succeeded(capture([*npm, "ci", "--prefix", project.frontend, "--offline", "--cache", cache,
                       "--no-audit", "--no-fund"], project, tool_env), "Frontend paket kurulumu")


def install_dependencies(project: Project, settings: SourceSettings, tool_env: dict, *, expected_python: Path | None = None) -> None:
    """Use one source per acquisition attempt; never fallback after installation fails."""
    _ensure_venv(project, tool_env, **({'expected_python': expected_python} if expected_python is not None else {}))
    node = tool_env.get('AWCENTER_MANAGED_NODE') or shutil.which('node', path=tool_env.get('PATH'))
    if not node:
        raise LauncherError('Node bulunamadı; paket güven deposu hazırlanamadı.')
    with package_trust_environment(tool_env, ca_file=settings.ca_file, python=project.python, node=node) as trusted_env, \
         tempfile.TemporaryDirectory(prefix="awcenter-packages-") as temporary:
        stage = Path(temporary)
        print("Python paketleri hazırlanıyor…", flush=True)
        _python_packages(project, settings, trusted_env, stage)
        print("Frontend paketleri hazırlanıyor…", flush=True)
        _frontend_packages(project, settings, trusted_env, stage)
