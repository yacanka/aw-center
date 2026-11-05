"""Acquire locked packages before installing; fallback is limited to availability."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .certificates import package_trust_environment
from .installation_sources import SourceSettings, acquisition_urls
from .model import LauncherError, Project, Scope
from .offline_manifest import verify_offline_manifest
from .process import controlled_run, environment

_STAGE_RECEIPT = '.awcenter-packages.json'
_FATAL_PACKAGE_FAILURES = (
    ((r'\b(?:sslerror|sslcertverificationerror|certificateerror|certificate_verify_failed)\b',
      r'\b(?:unable_to_verify_leaf_signature|unable_to_get_issuer_cert_locally|depth_zero_self_signed_cert|self_signed_cert_in_chain|cert_has_expired|cert_not_yet_valid|err_tls_cert_altname_invalid)\b',
      r'\b(?:ssl|tls) (?:certificate (?:verification|verify) failed|handshake (?:failed|failure)|routines)\b',
      r'\bcertificate (?:verification failed|verify failed|has expired)\b',
      r'\bself[- ]signed certificate\b',
      r'\bunable to (?:get local issuer certificate|verify the first certificate)\b'), 'package_tls_failed',
     'Paket bağlantısının TLS sertifikası veya güvenli bağlantısı doğrulanamadı.',
     'Sistem sertifika deposunu, kurumun onaylı CA dosyasını ve proxy erişimini kontrol edin.'),
    ((r'\beintegrity\b', r'\bhash mismatch\b',
      r'\bchecksum (?:verification )?(?:failed|failure|mismatch)\b',
      r'\bdo not match the hashes\b'), 'package_integrity_failed',
     'Paket dosyalarının bütünlüğü doğrulanamadı; dosyalar kullanılmadı.',
     'Onaylı paket veya depodan doğrulanmış dosyaları yeniden edinin; hash denetimini kapatmayın.'),
    ((r'\bno space\b', r'\benospc\b', r'\bdisk full\b'), 'package_disk_full',
     'Paket işlemi için yeterli disk alanı bulunamadı.',
     'Kurulum ve geçici dosya disklerinde boş alan açıp yeniden deneyin.'),
    ((r'\baccess is denied\b', r'\bpermission denied\b', r'\beacces\b', r'\beperm\b',
      r'\boperation not permitted\b'), 'package_access_denied',
     'Paket işlemi için gerekli dosya veya çalıştırma izni sağlanamadı.',
     'Seçili dizin ve araçların erişim izinlerini veya kurumun çalıştırma politikasını kontrol edin.'),
)


def _package_failure(output: str) -> tuple[str, str, str]:
    text = output.casefold()
    for patterns, code, message, remedy in _FATAL_PACKAGE_FAILURES:
        if any(re.search(pattern, text) for pattern in patterns):
            return code, message, remedy
    return ('package_command_failed', 'Paket aracı işlemi tamamlayamadı.',
            'Seçili paket kaynaklarını ve Python/Node araçlarını kontrol edip yeniden deneyin.')


class PackageCommandError(LauncherError):
    """Expose only reviewed package failure details, never tool diagnostics."""

    def __init__(self, result):
        self.code, message, self.remedy = _package_failure((result.stdout or '') + '\n' + (result.stderr or ''))
        if type(result.returncode) is int and result.returncode > 0:
            message += f' Süreç çıkış kodu: {result.returncode}.'
        super().__init__(message)


class PackageTimeoutError(LauncherError):
    """Identify a process timeout without retaining command or captured output."""

    code = 'package_timeout'
    remedy = 'Ağ ve paket araçlarının durumunu kontrol edip yeniden deneyin; tamamlanan aşamalar korunur.'

    def __init__(self):
        super().__init__('Paket işlemi süre sınırını aştı; kurulum yeniden çalıştırılabilir.')


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
    fatal = ("failed building wheel", "subprocess-exited-with-error", "eresolve")
    if _package_failure(text)[0] != 'package_command_failed' or any(value in text for value in fatal):
        return False
    codes = (408, 429, 500, 502, 503, 504) + ((401, 403, 407) if restricted else ())
    if any(re.search(rf'\b(?:e{code}|(?:http error|error|tunnel connection failed:)\s+{code}|{code}\s+client error)\b', text)
           for code in codes):
        return True
    return any(value in text for value in (
        "newconnectionerror", "connection refused", "connection reset", "readtimeouterror",
        "connecttimeouterror", "nameresolutionerror", "enotfound", "eai_again", "econnrefused",
        "econnreset", "err_socket_timeout", "etimedout", "http error 404", "e404",
        "503 service unavailable", "502 bad gateway", "504 gateway timeout",
    ))


def python_package_progress(line: str) -> str | None:
    """Translate reviewed pip events without exposing URLs, paths or diagnostics."""
    line = line.strip()
    name = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}"
    collecting = re.fullmatch(rf"Collecting ({name}(?:==[A-Za-z0-9_.+!-]+)?)(?: \(from [^\r\n]*\))?", line)
    if collecting:
        return f"Python: paket çözülüyor — {collecting[1]}"
    download = re.fullmatch(
        rf"(Downloading|Using cached) ({name}\.(?:whl|tar\.gz|zip)(?:\.metadata)?)"
        r"( \([0-9.]+ (?:bytes|kB|MB|GB)\))?", line)
    if download:
        action = 'indiriliyor' if download[1] == 'Downloading' else 'önbellekten alınıyor'
        return f"Python: {action} — {download[2]}{download[3] or ''}"
    building = re.fullmatch(rf"Building wheel for ({name}) \([A-Za-z0-9_.-]+\): started", line)
    if building:
        return f"Python: wheel derleniyor — {building[1]}"
    installing = re.fullmatch(rf"Installing collected packages: ({name}(?:, {name})*)", line)
    if installing:
        return f"Python: kuruluyor — {installing[1]}"[:1000]
    return None


def capture(command: list, project: Project, overrides: dict | None = None, *, timeout=1800, progress=None):
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
        # Package tools emit UTF-8, independently of the windowed Manager's
        # Windows ANSI code page. Native build-tool diagnostics may still use a
        # legacy encoding: retain their bytes as escapes, not a decoding crash.
        values.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        live_options = {}
        if progress is not None:
            values['PYTHONUNBUFFERED'] = '1'
            def report_line(line):
                message = python_package_progress(line)
                if message:
                    progress(message)
            live_options['on_output'] = report_line
        try:
            return controlled_run([str(part) for part in command], cwd=project.root, env=values,
                                  capture_output=True, text=True, encoding='utf-8', errors='backslashreplace',
                                  timeout=timeout, check=False,
                                  safe_boundary=any(str(part) == "migrate" for part in command), **live_options)
        except subprocess.TimeoutExpired:
            raise PackageTimeoutError() from None


def _succeeded(result, stage: str) -> None:
    if result.returncode:
        raise PackageCommandError(result)


def _offline_candidates(settings: SourceSettings):
    roots = []
    if settings.repository and not str(settings.repository).startswith("https://"):
        roots.append(Path(settings.repository))
    if settings.offline_dir:
        roots.append(Path(settings.offline_dir))
    roots.extend(settings.runtime_dirs)
    for root in dict.fromkeys(map(Path, roots)):
        for directory in (root / "dependencies", root):
            if (directory / "manifest.json").is_file():
                yield directory


def _offline_dependencies(project: Project, settings: SourceSettings) -> Path | None:
    for candidate in _offline_candidates(settings):
        verify_offline_manifest(project, Scope(), candidate)
        return candidate
    return None


class VirtualEnvironmentError(LauncherError):
    """A known venv compatibility failure, distinct from package or storage errors."""

    def __init__(self, reason, *, repairable=True):
        messages = {
            'incomplete': 'Mevcut .venv eksik.',
            'interrupted': 'Yarım sanal ortam başka Python veya kaynağa bağlı.',
            'version': 'Mevcut .venv CPython 3.11 x64 ile oluşturulmalı.',
            'python_mismatch': 'Mevcut .venv farklı bir Python kullanıyor.',
            'unusable': 'Mevcut .venv Python süreci başlatılamadı.',
        }
        self.code = 'venv_' + reason
        self.repairable = repairable
        self.remedy = 'Manager üzerinden Hazırla ve Başlat işlemini yeniden çalıştırın; önceki sanal ortam korunarak yenisi hazırlanır.'
        if not repairable:
            self.remedy = ('Oluşturulan ortam korunuyor; seçilen Python kurulumunun çalışabildiğini doğrulayın. '
                           'Yeniden denemede aynı ortam denetlenir, tekrar yedeklenmez.')
        super().__init__(messages[reason])


class VirtualEnvironmentRepairError(LauncherError):
    """A replacement could not safely preserve the existing environment."""

    code = 'venv_repair_failed'
    remedy = ('Bu kaynak dizininin .venv ortamını kullanan süreçleri kapatıp bağımsız Manager ile yeniden deneyin. '
              'Kaynak dizini erişim izinlerini ve disk alanını kontrol edin; .venv veya profil verilerini silmeyin.')

    def __init__(self, error=None):
        message = 'Önceki sanal ortam güvenli biçimde yedeklenemedi; mevcut .venv değiştirilmedi.'
        for label, value in (('WinError', getattr(error, 'winerror', None)),
                             ('errno', getattr(error, 'errno', None))):
            if type(value) is int and value > 0:
                message += f' {label}: {value}.'
        super().__init__(message)


def _same_python(first: Path, second: Path) -> bool:
    """Accept filesystem aliases without treating a different interpreter as equal."""
    try:
        if first.samefile(second):
            return True
    except OSError:
        pass
    return os.path.normcase(str(first.resolve())) == os.path.normcase(str(second.resolve()))


def _preserve_venv(project: Project, expected_python: Path) -> None:
    from .installation_permissions import require_unlinked, secure_path
    from .process import check_cancelled
    check_cancelled()
    require_unlinked(project.venv)
    paths = (expected_python, Path(sys.executable), Path(sys.prefix))
    if (not project.venv.is_dir() or not expected_python.is_file() or
            any(path.absolute().is_relative_to(project.venv.absolute()) or
                path.resolve().is_relative_to(project.venv.resolve()) for path in paths)):
        raise VirtualEnvironmentRepairError()
    try:
        # Stay on the source volume and in generated state excluded from Git and
        # release inventories. A unique wrapper prevents overwriting any backup.
        directory = project.root / '.runtime' / 'venv-backups'
        require_unlinked(directory)
        directory.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='preserved-', dir=directory))
        secure_path(backup)
        project.venv.rename(backup / '.venv')
    except OSError as error:
        raise VirtualEnvironmentRepairError(error) from None


def _ensure_venv(project: Project, tool_env: dict, *, expected_python: Path | None = None,
                 repair: bool = False, report=None) -> None:
    """Repair only declared venv failures under the caller's exclusive source lease.

    The old directory is retained, and a failed replacement keeps its creation
    marker so the same validated interpreter can resume it on the next attempt.
    Direct CLI callers retain the strict, non-replacing default.
    """
    existed = project.venv.exists()
    try:
        _prepare_venv(project, tool_env, expected_python=expected_python)
        return
    except VirtualEnvironmentError as error:
        if not repair or not existed or expected_python is None or not error.repairable:
            raise
    selected = Path(tool_env.get('AWCENTER_MANAGED_PYTHON') or expected_python)
    if not _same_python(selected, expected_python):
        raise VirtualEnvironmentRepairError()
    _preserve_venv(project, selected)
    if report:
        report('Önceki .venv .runtime/venv-backups altında korundu; seçilen Python ile yeni sanal ortam hazırlanıyor')
    _prepare_venv(project, {**tool_env, 'AWCENTER_MANAGED_PYTHON': str(selected)},
                  expected_python=expected_python)


def _prepare_venv(project: Project, tool_env: dict, *, expected_python: Path | None = None) -> None:
    from .installation_permissions import require_unlinked
    require_unlinked(project.venv)
    marker = project.venv / '.awcenter-creating.json'
    require_unlinked(marker)
    identity = {'version': 1, 'python': str(Path(tool_env.get('AWCENTER_MANAGED_PYTHON') or expected_python or project.python).resolve()),
                'source': str(project.root.resolve())}
    owned = False
    if marker.exists():
        try:
            saved = json.loads(marker.read_text(encoding='utf-8')) if marker.stat().st_size < 8192 else None
            if (isinstance(saved, dict) and isinstance(saved.get('python'), str)
                    and Path(saved['python']).is_absolute()):
                # Resume markers written by .pyw-based Manager versions. The
                # actual venv binding is still independently checked below.
                from .system_python import _console_python
                saved['python'] = str(_console_python(Path(saved['python'])).resolve())
            owned = saved == identity
        except (OSError, ValueError):
            pass
        if not owned:
            raise VirtualEnvironmentError('interrupted')
    if not project.python.is_file():
        if project.venv.exists() and not owned:
            raise VirtualEnvironmentError('incomplete')
        if not owned:
            project.venv.mkdir()
            with marker.open('x', encoding='utf-8') as stream:
                json.dump(identity, stream)
            owned = True
        _succeeded(capture([tool_env["AWCENTER_MANAGED_PYTHON"], "-m", "venv", project.venv], project,
                           tool_env), "Virtual environment oluşturma")
    try:
        result = capture([project.python, "-c", "import sys,struct; print(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8)"], project, tool_env)
    except OSError:
        raise VirtualEnvironmentError('unusable', repairable=not owned) from None
    if result.returncode or result.stdout.strip() != "True":
        raise VirtualEnvironmentError('version', repairable=not owned)
    if expected_python is not None:
        base = capture([project.python, '-I', '-B', '-c',
                        'import json,sys; print(json.dumps(getattr(sys, "_base_executable", sys.executable), ensure_ascii=True))'], project, tool_env)
        # -I ignores PYTHONUTF8. ASCII JSON keeps paths intact even when the
        # Windows child and Manager use different stdio code pages.
        try:
            value = json.loads(base.stdout) if not base.returncode and len(base.stdout) <= 64 * 1024 else None
            matches = (isinstance(value, str) and Path(value).is_absolute()
                       and _same_python(Path(value), Path(expected_python)))
        except (ValueError, OSError):
            matches = False
        if not matches:
            raise VirtualEnvironmentError('python_mismatch', repairable=not owned)
    if owned:
        # A crash can occur after python.exe appears but before ensurepip ends.
        _succeeded(capture([project.python, '-m', 'ensurepip', '--upgrade'], project, tool_env), 'pip hazırlığı')
        marker.unlink()


def _python_packages(project: Project, settings: SourceSettings, tool_env: dict, stage: Path) -> None:
    if not project.requirements:
        raise LauncherError("Python requirements lock dosyası bulunamadı.")
    offline = _offline_dependencies(project, settings)
    wheelhouse = offline / 'wheels' if offline else None
    indexes = acquisition_urls(settings, "https://pypi.org/simple", settings.python_index_url)
    for number, index in enumerate(indexes if wheelhouse is None else []):
        candidate = stage / f'wheels-{number}'
        candidate.mkdir()
        settings.report(f'Python paketleri: izinli kaynak {number + 1}/{len(indexes)} deneniyor')
        result = capture([project.python, "-m", "pip", "wheel", "--wheel-dir", candidate,
                          "--index-url", index, "-r", project.requirements], project, tool_env, progress=settings.progress)
        if not result.returncode:
            wheelhouse = candidate
            break
        if not availability_failure(result.stdout + result.stderr, restricted=True):
            _succeeded(result, "Python paket edinimi")
        settings.report('Python paket kaynağı erişilemiyor; sıradaki izinli kaynak deneniyor')
    if wheelhouse is None:
        offline = _offline_dependencies(project, settings)
        if not offline:
            raise LauncherError("Kilitli Python paketleri internet, seçilen depo veya offline dizinde bulunamadı.")
        wheelhouse = offline / "wheels"
    _succeeded(capture([project.python, "-m", "pip", "install", "--no-index", "--find-links", wheelhouse,
                       "-r", project.requirements], project, tool_env, progress=settings.progress), "Python paket kurulumu")
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
    offline = _offline_dependencies(project, settings)
    cache = None
    timeout_error = None
    registries = acquisition_urls(settings, "https://registry.npmjs.org", settings.npm_registry_url)
    for number, registry in enumerate(registries if offline is None else []):
        tree, candidate = stage / f'npm-source-{number}', stage / f'npm-cache-{number}'
        tree.mkdir()
        for name in ('package.json', 'package-lock.json'):
            source = project.frontend / name
            if not source.is_file():
                raise LauncherError('Frontend lock dosyası eksik.')
            shutil.copyfile(source, tree / name)
        settings.report(f'npm paketleri: izinli kaynak {number + 1}/{len(registries)} deneniyor')
        try:
            result = capture([*npm, "ci", "--prefix", tree, "--ignore-scripts", "--cache", candidate,
                              "--registry", registry, "--replace-registry-host=npmjs", "--no-audit", "--no-fund"],
                             project, tool_env)
        except PackageTimeoutError as error:
            timeout_error = error
            settings.report('npm kaynağı süre sınırında yanıt vermedi; sıradaki izinli kaynak deneniyor')
            continue
        timeout_error = None
        if not result.returncode:
            cache = candidate
            break
        if not availability_failure(result.stdout + result.stderr, restricted=True):
            _succeeded(result, "npm paket edinimi")
        settings.report('npm kaynağı erişilemiyor; sıradaki izinli kaynak deneniyor')
    if cache is None:
        offline = offline or _offline_dependencies(project, settings)
        if not offline:
            if timeout_error is not None:
                raise timeout_error
            raise LauncherError("Kilitli npm paketleri internet, seçilen depo veya offline dizinde bulunamadı.")
        cache = stage / "offline-npm-cache"
        shutil.copytree(offline / "npm-cache", cache)
    _succeeded(capture([*npm, "ci", "--prefix", project.frontend, "--offline", "--cache", cache,
                       "--no-audit", "--no-fund"], project, tool_env), "Frontend paket kurulumu")


def install_dependencies(project: Project, settings: SourceSettings, tool_env: dict, *, expected_python: Path | None = None,
                         repair_venv: bool = False) -> None:
    """Use one source per acquisition attempt; never fallback after installation fails."""
    settings.report('Python sanal ortamı doğrulanıyor')
    _ensure_venv(project, tool_env, expected_python=expected_python,
                 repair=repair_venv, report=settings.report)
    node = tool_env.get('AWCENTER_MANAGED_NODE') or shutil.which('node', path=tool_env.get('PATH'))
    if not node:
        raise LauncherError('Node bulunamadı; paket güven deposu hazırlanamadı.')
    settings.report('Paket bağlantıları için güven deposu hazırlanıyor')
    with package_trust_environment(tool_env, ca_file=settings.ca_file, python=project.python,
                                   node=node, progress=settings.report) as trusted_env, \
         tempfile.TemporaryDirectory(prefix="awcenter-packages-") as temporary:
        stage = Path(temporary)
        print("Python paketleri hazırlanıyor…", flush=True)
        settings.report('Python bağımlılıkları hazırlanıyor')
        if not dependency_stage(project.venv, project.requirements,
                                lambda: _python_packages(project, settings, trusted_env, stage)):
            settings.report('Python bağımlılıkları doğrulandı; tamamlanmış aşama kullanılıyor')
        print("Frontend paketleri hazırlanıyor…", flush=True)
        settings.report('Frontend bağımlılıkları hazırlanıyor')
        if not dependency_stage(project.frontend / 'node_modules', project.frontend / 'package-lock.json',
                                lambda: _frontend_packages(project, settings, trusted_env, stage)):
            settings.report('npm bağımlılıkları doğrulandı; tamamlanmış aşama kullanılıyor')
