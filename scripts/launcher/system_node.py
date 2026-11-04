"""Discover operator-installed Node and its pinned npm CLI without installing."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from .model import LauncherError
from .process import controlled_run, environment

PROBE_TIMEOUT_SECONDS = 30
_PROBE = 'console.log(JSON.stringify({execPath:process.execPath,version:process.version,arch:process.arch,platform:process.platform}))'
_VERSION = re.compile(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
_FAILURES = {
    'not_found': ('Uyumlu sistem Node.js x64 bulunamadı.', 'Node komutu / yolu alanına kurulu Node dosyasını girin; Node 22.12+ (22.x) veya 24+ kullanın.'),
    'path_missing': ('Seçilen Node dosyası veya komutu bulunamadı.', 'node.exe dosyasını, kurulum dizinini veya node komutunu seçin.'),
    'excluded': ('Seçilen yol sistem Node olarak kullanılamıyor.', 'AW Center yönetilen runtime dizini veya komut betiği yerine kurulu Node yürütülebilir dosyasını seçin.'),
    'start_failed': ('Node denetim süreci başlatılamadı.', 'Node yürütülebilir dosyasını ve uygulama çalıştırma politikasını kontrol edin.'),
    'process_failed': ('Node denetim süreci hata ile kapandı.', 'Node kurulumunu ve gerekli sistem bileşenlerini kontrol edin.'),
    'timeout': ('Node denetimi süre sınırını aştı.', 'Seçilen Node dosyasının aynı bilgisayarda çalışabildiğini ve güvenlik yazılımını kontrol edin.'),
    'invalid_response': ('Node beklenen denetim yanıtını vermedi.', 'Ek çıktı üreten bir wrapper yerine kurulu Node yürütülebilir dosyasını seçin.'),
    'version': ('Node sürümü uyumsuz; Node 22.12+ (22.x) veya 24+ gerekiyor.', 'Kararlı Node 22.12+ (22.x) veya 24+ x64 kurulumunu seçin; ön sürümler desteklenmiyor.'),
    'architecture': ('Node mimarisi uyumsuz; x64 gerekiyor.', 'x64 Node kurulumunu seçin; ARM64 ve 32 bit desteklenmiyor.'),
    'platform': ('Node platformu uyumsuz; Windows Node gerekiyor.', 'Windows x64 node.exe dosyasını seçin.'),
}


class SystemNodeError(LauncherError):
    """Safe probe details; private paths, commands and stderr are never reported."""

    def __init__(self, reason, *, system_error=None, returncode=None):
        self.reason = reason if reason in _FAILURES else 'invalid_response'
        self.code = 'system_node_' + self.reason
        message, self.remedy = _FAILURES[self.reason]
        for label, value in (('WinError', getattr(system_error, 'winerror', None)),
                             ('errno', getattr(system_error, 'errno', None)), ('Süreç çıkış kodu', returncode)):
            if type(value) is int:
                message += f' {label}: {value}.'
        super().__init__(message)


def _probe_environment():
    return environment({'NODE_OPTIONS': '', 'NODE_PATH': '', 'NODE_TLS_REJECT_UNAUTHORIZED': '1'})


def _probe(executable):
    try:
        result = controlled_run([str(executable), '--eval', _PROBE], env=_probe_environment(),
                                capture_output=True, text=True, encoding='utf-8', timeout=PROBE_TIMEOUT_SECONDS, check=False)
        if result.returncode:
            raise SystemNodeError('process_failed', returncode=result.returncode)
        if len(result.stdout) > 4096:
            raise SystemNodeError('invalid_response')
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise SystemNodeError('invalid_response')
        version = value.get('version')
        match = _VERSION.fullmatch(version) if isinstance(version, str) else None
        if not match:
            raise SystemNodeError('version')
        major, minor, _patch = map(int, match.groups())
        if not (major == 22 and minor >= 12 or major >= 24):
            raise SystemNodeError('version')
        if value.get('arch') != 'x64':
            raise SystemNodeError('architecture')
        if sys.platform == 'win32' and value.get('platform') != 'win32':
            raise SystemNodeError('platform')
        actual = value.get('execPath')
        if not isinstance(actual, str):
            raise SystemNodeError('invalid_response')
        path = Path(actual)
        if not path.is_absolute() or not path.is_file():
            raise SystemNodeError('invalid_response')
        return path.resolve()
    except subprocess.TimeoutExpired:
        raise SystemNodeError('timeout') from None
    except OSError as error:
        raise SystemNodeError('path_missing' if isinstance(error, FileNotFoundError) else 'start_failed', system_error=error) from None
    except (ValueError, TypeError, AttributeError):
        raise SystemNodeError('invalid_response') from None


def _excluded(path):
    path = Path(path).resolve()
    if path.suffix.lower() in {'.cmd', '.bat'}:
        return True
    if local := os.environ.get('LOCALAPPDATA'):
        if path.is_relative_to((Path(local) / 'AWCenter/runtimes').resolve()):
            return True
    # Custom installation homes retain the same reviewed-runtime receipt marker.
    return any((parent / '.awcenter-tool.json').exists() for parent in path.parents)


def validate_node(executable: Path) -> Path:
    """Require a stable x64 Node 22.12+ in major 22, or 24+; never install."""
    path = Path(executable)
    if not path.is_absolute() or not path.is_file():
        raise SystemNodeError('path_missing')
    path = path.resolve()
    if _excluded(path):
        raise SystemNodeError('excluded')
    actual = _probe(path)
    if _excluded(actual):
        raise SystemNodeError('excluded')
    if actual != path and _probe(actual) != actual:
        raise SystemNodeError('invalid_response')
    return actual


def _path_candidates(name):
    filename = name + '.exe' if sys.platform == 'win32' and not name.lower().endswith('.exe') else name
    for directory in os.get_exec_path():
        if not directory:
            continue
        candidate = Path(directory.strip('"')).absolute() / filename
        if executable := shutil.which(str(candidate)):
            yield Path(executable)


def _windows_candidates():
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'Software\Node.js', 0, winreg.KEY_READ | view) as key:
                    directory = winreg.QueryValueEx(key, 'InstallPath')[0]
                    if isinstance(directory, str):
                        yield Path(directory) / 'node.exe'
            except OSError:
                continue
    for variable, relative in (('ProgramFiles', 'nodejs/node.exe'),
                               ('ProgramW6432', 'nodejs/node.exe'),
                               ('ProgramFiles(x86)', 'nodejs/node.exe'),
                               ('LOCALAPPDATA', 'Programs/nodejs/node.exe')):
        if directory := os.environ.get(variable):
            yield Path(directory) / relative


def _candidates():
    yield from _path_candidates('node')
    if sys.platform == 'win32':
        yield from _windows_candidates()


def _selected_candidates(selection):
    value = selection.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    if not value or len(value) > 8192 or any(character in value for character in '\0\r\n'):
        raise SystemNodeError('path_missing')
    path = Path(value).expanduser()
    if path.is_dir():
        yield (path / ('node.exe' if sys.platform == 'win32' else 'node')).resolve()
    elif path.is_file():
        yield path.resolve()
    elif not any(separator in value for separator in ('/', '\\')):
        yield from _path_candidates(value)


def discover_node(selection: str | None = None) -> Path:
    """Validate a command, executable or directory; explicit input never falls back.

    Automatic discovery inspects every PATH entry before Windows registry/default
    locations. Shell expressions and Node's script arguments are never parsed.
    """
    failures = []
    seen = set()
    for candidate in (_selected_candidates(selection) if selection else _candidates()):
        path = Path(candidate).resolve()
        identity = os.path.normcase(str(path))
        if identity in seen:
            continue
        seen.add(identity)
        try:
            return validate_node(path)
        except SystemNodeError as error:
            failures.append(error)
    meaningful = [error for error in failures if error.reason not in {'path_missing', 'excluded'}]
    if meaningful:
        raise meaningful[-1]
    if failures:
        raise failures[-1]
    raise SystemNodeError('path_missing' if selection else 'not_found')


def _npm_candidates(node):
    for directory in (Path(node).parent, Path(node).resolve().parent):
        for relative in ('node_modules/npm/bin/npm-cli.js', '../lib/node_modules/npm/bin/npm-cli.js',
                         '../libexec/lib/node_modules/npm/bin/npm-cli.js',
                         '../share/nodejs/npm/bin/npm-cli.js'):
            yield (directory / relative).resolve()


def find_npm_cli(node: Path, version: str) -> Path | None:
    """Find exact pinned npm beside validated Node; execute JS directly, never CMD.

    Missing or incompatible npm permits managed npm acquisition. Cancellation
    propagates so stopping an operation can never initiate a fallback download.
    """
    seen = set()
    for cli in _npm_candidates(node):
        identity = os.path.normcase(str(cli))
        if identity in seen or not cli.is_file() or _excluded(cli):
            continue
        seen.add(identity)
        try:
            result = controlled_run([str(node), str(cli), '--version'], env=_probe_environment(),
                                    capture_output=True, text=True, encoding='utf-8', timeout=PROBE_TIMEOUT_SECONDS, check=False)
            if result.returncode == 0 and result.stdout.strip() == version:
                return cli
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError):
            continue
    return None
