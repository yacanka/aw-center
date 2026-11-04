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

_STAGE_RECEIPT = '.awcenter-packages.json'


def _package_inventory(target):
    from .installation_permissions import require_unlinked
    from .offline_manifest import file_sha256
    result = {}
    for current, directories, files in os.walk(target, followlinks=False):
        for name in (*directories, *files):
            require_unlinked(Path(current) / name)
        directories[:] = [name for name in directories if name not in {'__pycache__', '.vite', '.cache'}]
        for name in files:
            path = Path(current) / name
            if path == target / _STAGE_RECEIPT or path.suffix == '.pyc':
                continue
            if not path.is_file():
                raise LauncherError('Bağımlılık dizini yalnız normal dosyalar içermeli.')
            result[path.relative_to(target).as_posix()] = file_sha256(path)
    return result


def dependency_stage(target: Path, lock: Path, install) -> bool:
    """Reuse only a completed stage with the same lock and verified installed bytes."""
    from .installation_bundle import _json_object
    from .installation_permissions import require_unlinked
    from .offline_manifest import file_sha256
    receipt = target / _STAGE_RECEIPT
    require_unlinked(target)
    require_unlinked(receipt)
    identity = file_sha256(lock)
    if receipt.exists():
        saved = _json_object(receipt)
        if saved.get('version') != 1:
            raise LauncherError('Bağımlılık aşama kaydı geçersiz; mevcut ortam değiştirilmedi.')
        if saved.get('lock') == identity:
            if saved.get('files') != _package_inventory(target):
                raise LauncherError('Tamamlanmış bağımlılık dosyaları değişmiş; mevcut ortam otomatik değiştirilmedi.')
            return False
    install()
    saved = {'version': 1, 'lock': identity, 'files': _package_inventory(target)}
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target, delete=False) as output:
        temporary = Path(output.name)
        json.dump(saved, output, sort_keys=True)
    try:
        os.replace(temporary, receipt)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def availability_failure(output: str, *, restricted: bool = False) -> bool:
    """Package managers have no common typed network error protocol; fail closed.

    Only their explicit transport/not-found signatures permit source fallback.
    Unknown failures are installation failures, even if that requires a manual retry.
    """
    text = output.casefold()
    fatal = ("certificate", "sslerror", "eintegrity", "hash mismatch", "failed building wheel",
             "subprocess-exited-with-error", "eresolve", "no space", "access is denied", "permission denied")
    if any(value in text for value in fatal):
        return False
    if restricted and any(value in text for code in (401, 403, 407)
                          for value in (f'http error {code}', f'error {code}', f'e{code}', f'{code} client error')):
        return True
    return any(value in text for value in (
        "newconnectionerror", "connection refused", "connection reset", "readtimeouterror",
        "connecttimeouterror", "nameresolutionerror", "enotfound", "eai_again", "econnrefused",
        "econnreset", "err_socket_timeout", "etimedout", "http error 404", "e404",
        "503 service unavailable", "502 bad gateway", "504 gateway timeout",
    ))


def capture(command: list, project: Project, overrides: dict | None = None, *, timeout=1800):
    """Capture diagnostics privately while isolating inherited package settings."""
    values = environment(overrides)
    values = {key: value for key, value in values.items()
              if not key.upper().startswith(("PIP_", "NPM_CONFIG_"))}
    values.update({"PIP_CONFIG_FILE": os.devnull, "PIP_NO_INPUT": "1",
                   "PIP_NO_CACHE_DIR": "1",
                   "PIP_DEFAULT_TIMEOUT": "10", "PIP_RETRIES": "1",
                   "NODE_TLS_REJECT_UNAUTHORIZED": "1", "NPM_CONFIG_STRICT_SSL": "true",
                   "NPM_CONFIG_FETCH_RETRIES": "1", "NPM_CONFIG_FETCH_TIMEOUT": "15000"})
    with tempfile.TemporaryDirectory(prefix="awcenter-package-config-") as temporary:
        # npm rejects loading the same file as both user and global config,
        # including the null device. Separate empty files suppress both sources.
        for kind in ("user", "global"):
            path = Path(temporary) / (kind + ".npmrc")
            path.write_bytes(b"")
            values["NPM_CONFIG_" + kind.upper() + "CONFIG"] = str(path)
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
    from .installation_permissions import require_unlinked
    require_unlinked(project.venv)
    marker = project.venv / '.awcenter-creating.json'
    require_unlinked(marker)
    identity = {'version': 1, 'python': str(Path(tool_env.get('AWCENTER_MANAGED_PYTHON') or expected_python or project.python).resolve()),
                'source': str(project.root.resolve())}
    owned = False
    if marker.exists():
        try:
            owned = marker.stat().st_size < 8192 and json.loads(marker.read_text(encoding='utf-8')) == identity
        except (OSError, ValueError):
            pass
        if not owned:
            raise LauncherError('Yarım sanal ortam başka Python veya kaynağa bağlı; mevcut dosyalar değiştirilmedi.')
    if not project.python.is_file():
        if project.venv.exists() and not owned:
            raise LauncherError("Mevcut .venv eksik; otomatik silinmedi. Ayrı temiz kaynak dizini kullanın.")
        if not owned:
            project.venv.mkdir()
            with marker.open('x', encoding='utf-8') as stream:
                json.dump(identity, stream)
            owned = True
        _succeeded(capture([tool_env["AWCENTER_MANAGED_PYTHON"], "-m", "venv", project.venv], project,
                           tool_env), "Virtual environment oluşturma")
    result = capture([project.python, "-c", "import sys,struct; print(sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8)"], project, tool_env)
    if result.returncode or result.stdout.strip() != "True":
        raise LauncherError("Mevcut .venv CPython 3.11 x64 ile oluşturulmalı; otomatik değiştirilmedi.")
    if expected_python is not None:
        base = capture([project.python, '-I', '-B', '-c',
                        'import sys; print(getattr(sys, "_base_executable", sys.executable))'], project, tool_env)
        if (base.returncode or not base.stdout.strip() or
                Path(base.stdout.strip()).resolve() != Path(expected_python).resolve()):
            raise LauncherError('Mevcut .venv farklı bir Python kullanıyor; otomatik değiştirilmedi. Ayrı temiz kaynak dizini kullanın.')
    if owned:
        # A crash can occur after python.exe appears but before ensurepip ends.
        _succeeded(capture([project.python, '-m', 'ensurepip', '--upgrade'], project, tool_env), 'pip hazırlığı')
        marker.unlink()


def _python_packages(project: Project, settings: SourceSettings, tool_env: dict, stage: Path) -> None:
    if not project.requirements:
        raise LauncherError("Python requirements lock dosyası bulunamadı.")
    offline = _offline_dependencies(project, settings) if settings.mode in {'restricted', 'offline'} else None
    wheelhouse = offline / 'wheels' if offline else None
    indexes = acquisition_urls(settings, "https://pypi.org/simple", settings.python_index_url)
    for number, index in enumerate(indexes if wheelhouse is None else []):
        candidate = stage / f'wheels-{number}'
        candidate.mkdir()
        result = capture([project.python, "-m", "pip", "wheel", "--wheel-dir", candidate,
                          "--index-url", index, "-r", project.requirements], project, tool_env)
        if not result.returncode:
            wheelhouse = candidate
            break
        if not availability_failure(result.stdout + result.stderr, restricted=settings.mode == 'restricted'):
            _succeeded(result, "Python paket edinimi")
        settings.report('Python paket kaynağı erişilemiyor; sıradaki izinli kaynak deneniyor')
    if wheelhouse is None:
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
    offline = _offline_dependencies(project, settings) if settings.mode in {'restricted', 'offline'} else None
    cache = None
    registries = acquisition_urls(settings, "https://registry.npmjs.org", settings.npm_registry_url)
    for number, registry in enumerate(registries if offline is None else []):
        tree, candidate = stage / f'npm-source-{number}', stage / f'npm-cache-{number}'
        tree.mkdir()
        for name in ('package.json', 'package-lock.json'):
            source = project.frontend / name
            if not source.is_file():
                raise LauncherError('Frontend lock dosyası eksik.')
            shutil.copyfile(source, tree / name)
        result = capture([*npm, "ci", "--prefix", tree, "--ignore-scripts", "--cache", candidate,
                          "--registry", registry, "--replace-registry-host=npmjs", "--no-audit", "--no-fund"],
                         project, tool_env)
        if not result.returncode:
            cache = candidate
            break
        if not availability_failure(result.stdout + result.stderr, restricted=settings.mode == 'restricted'):
            _succeeded(result, "npm paket edinimi")
        settings.report('npm kaynağı erişilemiyor; sıradaki izinli kaynak deneniyor')
    if cache is None:
        offline = offline or _offline_dependencies(project, settings)
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
        if not dependency_stage(project.venv, project.requirements,
                                lambda: _python_packages(project, settings, trusted_env, stage)):
            settings.report('Python bağımlılıkları doğrulandı; tamamlanmış aşama kullanılıyor')
        print("Frontend paketleri hazırlanıyor…", flush=True)
        if not dependency_stage(project.frontend / 'node_modules', project.frontend / 'package-lock.json',
                                lambda: _frontend_packages(project, settings, trusted_env, stage)):
            settings.report('npm bağımlılıkları doğrulandı; tamamlanmış aşama kullanılıyor')
