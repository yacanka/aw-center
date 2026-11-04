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

_ERROR = 'Uygun sistem Python 3.11 x64 bulunamadı. Python komutu / yolu alanına python veya python.exe yolunu girin; gerekirse “Python çalışma zamanını kur” seçeneğini işaretleyin.'
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


def _path_candidates(name):
    # which() alone stops at a Store alias or an incompatible Python. Inspect
    # each PATH entry so a later, usable installation still gets a chance.
    filename = name + '.exe' if os.name == 'nt' and not name.lower().endswith('.exe') else name
    for directory in os.get_exec_path():
        # An absolute candidate also prevents Python 3.11's Windows which()
        # from prepending cwd, bypassing the directory currently being checked.
        candidate = Path(directory.strip('"')).absolute() / filename
        if directory and (executable := shutil.which(str(candidate))):
            yield [executable]


def _windows_candidates():
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            for version in ('3.11', '3.11-64'):
                try:
                    with winreg.OpenKey(hive, f'Software\\Python\\PythonCore\\{version}\\InstallPath',
                                        0, winreg.KEY_READ | view) as key:
                        try:
                            executable = winreg.QueryValueEx(key, 'ExecutablePath')[0]
                        except OSError:
                            executable = str(Path(winreg.QueryValueEx(key, '')[0]) / 'python.exe')
                        yield [executable]
                except OSError:
                    continue
    for variable, relative in (('LOCALAPPDATA', 'Programs/Python/Python311/python.exe'),
                               ('ProgramFiles', 'Python311/python.exe'),
                               ('ProgramW6432', 'Python311/python.exe'),
                               ('SystemDrive', '/Python311/python.exe')):
        if directory := os.environ.get(variable):
            yield [directory + relative if variable == 'SystemDrive' else str(Path(directory) / relative)]


def _candidates():
    if not getattr(sys, 'frozen', False):
        yield [getattr(sys, '_base_executable', sys.executable)]
    for command in _path_candidates('py'):
        yield [*command, '-3.11']
    for name in ('python3.11', 'python', 'python3'):
        yield from _path_candidates(name)
    if os.name == 'nt':
        yield from _windows_candidates()


def _selected_candidates(selection):
    value = selection.strip().strip('"')
    if not value or len(value) > 8192 or any(character in value for character in '\0\r\n'):
        raise LauncherError(_ERROR)
    path = Path(value).expanduser()
    if path.is_dir():
        yield [str(path / ('python.exe' if os.name == 'nt' else 'python3.11'))]
    elif path.is_file():
        yield [str(path.resolve())]
    elif value in {'py', 'py -3.11'}:
        for command in _path_candidates('py'):
            yield [*command, '-3.11']
    elif not any(separator in value for separator in ('/', '\\')):
        yield from _path_candidates(value)


def discover_python(selection: str | None = None) -> Path:
    """Validate a command/file/directory, or discover CPython without installing.

    An explicit selection never falls back to a different interpreter. Commands
    are executable names, not shell expressions; only py's 3.11 selector is allowed.
    """
    seen = set()
    for command in (_selected_candidates(selection) if selection else _candidates()):
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
