"""Discover and validate an operator-installed CPython without installing it."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .model import LauncherError
from .process import controlled_run, environment
from .process import OperationCancelled

_ERROR = 'Uygun sistem Python 3.11 x64 bulunamadı. Python 3.11 x64 kurun veya “Python çalışma zamanını kur” seçeneğini işaretleyin.'
_PROBE = ('import json,sys,struct,sysconfig,venv,ensurepip; '
          'print(json.dumps({"version":list(sys.version_info[:2]),"bits":struct.calcsize("P")*8,'
          '"platform":sysconfig.get_platform(),'
          '"implementation":sys.implementation.name,"executable":sys.executable,'
          '"base":getattr(sys,"_base_executable",sys.executable)}))')


def _probe(command):
    values = environment({'PYTHONHOME': '', 'PYTHONPATH': '', 'PYTHONSTARTUP': '',
                          'PYTHONUSERBASE': '', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                          'PYTHON_MANAGER_AUTOMATIC_INSTALL': 'false'})
    # The legacy launcher enables install-on-demand by variable presence, even 0.
    values.pop('PYLAUNCHER_ALLOW_INSTALL', None)
    try:
        result = controlled_run([*map(str, command), '-I', '-S', '-B', '-X', 'utf8', '-c', _PROBE],
                                env=values, capture_output=True, text=True, timeout=5, check=False)
        if result.returncode or len(result.stdout) > 4096:
            return None
        value = json.loads(result.stdout)
        if (value.get('version') != [3, 11] or value.get('bits') != 64 or
                (sys.platform == 'win32' and value.get('platform') != 'win-amd64') or
                value.get('implementation') != 'cpython' or not isinstance(value.get('base'), str)):
            return None
        base = Path(value['base'])
        if not base.is_absolute() or not base.is_file():
            return None
        return base.resolve()
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError):
        return None


def _excluded(path):
    normalized = str(path).replace('\\', '/').lower()
    if '/microsoft/windowsapps/' in normalized:
        return True  # Never activate the Microsoft Store execution alias.
    local = os.environ.get('LOCALAPPDATA')
    if local:
        return path.resolve().is_relative_to((Path(local) / 'AWCenter/runtimes').resolve())
    return False


def validate_python(executable: Path) -> Path:
    """Require full CPython 3.11 x64 with venv/ensurepip; never use a frozen EXE."""
    path = Path(executable)
    if not path.is_absolute() or not path.is_file() or _excluded(path):
        raise LauncherError(_ERROR)
    base = _probe([path])
    if base is None or _excluded(base):
        raise LauncherError(_ERROR)
    if base != path.resolve():
        # A Python running from a venv is a discovery hint, not the base pointer.
        return validate_python(base)
    return base


def _candidates():
    if not getattr(sys, 'frozen', False):
        yield [getattr(sys, '_base_executable', sys.executable)]
    if launcher := shutil.which('py'):
        yield [launcher, '-3.11']
    for name in ('python3.11', 'python', 'python3'):
        if executable := shutil.which(name):
            if not _excluded(Path(executable)):
                yield [executable]
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for version in ('3.11', '3.11-64'):
                try:
                    with winreg.OpenKey(hive, f'Software\\Python\\PythonCore\\{version}\\InstallPath',
                                        0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                        yield [str(Path(winreg.QueryValueEx(key, '')[0]) / 'python.exe')]
                except OSError:
                    continue


def discover_python() -> Path:
    """Try local CPython/py launcher/PATH/Windows registrations, without network."""
    seen = set()
    for command in _candidates():
        identity = tuple(map(str, command))
        if identity in seen or _excluded(Path(command[0])):
            continue
        seen.add(identity)
        base = _probe(command)
        if base is not None:
            try:
                return validate_python(base)
            except OperationCancelled:
                raise
            except LauncherError:
                continue
    raise LauncherError(_ERROR)
