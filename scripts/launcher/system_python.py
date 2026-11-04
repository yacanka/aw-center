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

PROBE_TIMEOUT_SECONDS = 60

_ERROR = 'Uygun sistem Python 3.11 x64 bulunamadı. Python komutu / yolu alanına python veya python.exe yolunu girin; gerekirse “Python çalışma zamanını kur” seçeneğini işaretleyin.'
_PROBE = '''import json, sys, struct
value = {"version": list(sys.version_info[:2]), "micro": sys.version_info.micro,
         "bits": struct.calcsize("P") * 8, "implementation": sys.implementation.name,
         "base": getattr(sys, "_base_executable", None) or sys.executable, "modules": {}}
for name in ("sysconfig", "venv", "ensurepip"):
    try:
        module = __import__(name)
        if name == "sysconfig":
            value["platform"] = module.get_platform()
        value["modules"][name] = "ok"
    except ModuleNotFoundError as error:
        value["modules"][name] = "missing" if error.name == name else "failed"
    except Exception:
        value["modules"][name] = "failed"
print(json.dumps(value))
'''
_FAILURES = {
    'not_found': (_ERROR, 'Python komutu / yolu alanına python, py -3.11 veya python.exe yolunu girin.'),
    'path_missing': ('Seçilen Python dosyası veya komutu bulunamadı.', 'python.exe dosyasını seçin; CMD’de python -c "import sys; print(sys.executable)" ile konumunu kontrol edebilirsiniz.'),
    'excluded': ('Seçilen yol sistem Python’u olarak kullanılamıyor.', 'Microsoft Store alias’ı veya AW Center yönetilen runtime dizini yerine kurulu python.exe dosyasını seçin.'),
    'start_failed': ('Python denetim süreci başlatılamadı.', 'Dosyanın python.exe olduğunu ve Windows uygulama çalıştırma politikasını kontrol edin; sayısal sistem kodunu inceleyin.'),
    'process_failed': ('Python denetim süreci hata ile kapandı.', 'Süreç çıkış koduyla Python kurulumunu ve gerekli DLL dosyalarını kontrol edin.'),
    'timeout': (f'Python denetimi {PROBE_TIMEOUT_SECONDS} saniyelik süre sınırını aştı.', 'Seçilen python.exe dosyasının aynı bilgisayarda CMD’den çalışabildiğini ve güvenlik yazılımının süreç başlatmayı geciktirip geciktirmediğini kontrol edin.'),
    'invalid_response': ('Python beklenen denetim yanıtını vermedi.', 'python.exe seçin; komutun ek çıktı üreten bir wrapper olmadığını ve Python kurulumunu kontrol edin.'),
    'version': ('Python sürümü uyumsuz; CPython 3.11 gerekiyor.', '3.11.x kurulumunu seçin. 3.11.3 dahil 3.11 yama sürümleri kabul edilir.'),
    'architecture': ('Python mimarisi uyumsuz; Windows x64 gerekiyor.', '64 bit AMD64 CPython 3.11 kurulumunu seçin; ARM64 ve 32 bit yorumlayıcılar desteklenmiyor.'),
    'implementation': ('Yorumlayıcı CPython değil.', 'Tam CPython 3.11 x64 kurulumunu seçin.'),
    'venv_missing': ('Python bulundu fakat venv modülü eksik.', 'Tam CPython kurulumunu venv desteğiyle onarın; mevcut sanal ortamı silmeyin.'),
    'ensurepip_missing': ('Python bulundu fakat ensurepip modülü eksik.', 'Tam CPython kurulumunu pip/ensurepip desteğiyle onarın veya başka tam bir CPython 3.11 x64 seçin.'),
    'module_failed': ('Python bulundu fakat sysconfig, venv veya ensurepip modülü yüklenemedi.', 'Tam Python kurulumundaki standart modül ve DLL dosyalarını kontrol edin; başka tam bir CPython 3.11 x64 seçebilirsiniz.'),
    'base_missing': ('Python’un temel yorumlayıcı dosyası doğrulanamadı.', 'Sanal ortamın değil, tam CPython kurulumundaki python.exe dosyasını seçin.'),
}


class SystemPythonError(LauncherError):
    """A reviewed probe failure; raw command, paths and stderr never enter reports."""

    def __init__(self, reason, *, system_error=None, returncode=None, version=None, bits=None, module=None):
        self.reason = reason if reason in _FAILURES else 'invalid_response'
        self.code = 'system_python_' + self.reason
        message, self.remedy = _FAILURES[self.reason]
        for label, value in (('WinError', getattr(system_error, 'winerror', None)),
                             ('errno', getattr(system_error, 'errno', None)), ('Süreç çıkış kodu', returncode)):
            if type(value) is int:
                message += f' {label}: {value}.'
        if isinstance(version, list) and 2 <= len(version) <= 3 and all(type(part) is int for part in version):
            message += ' Algılanan sürüm: ' + '.'.join(map(str, version)) + '.'
        if type(bits) is int:
            message += f' Algılanan bit: {bits}.'
        if module in ('sysconfig', 'venv', 'ensurepip'):
            message += f' Başarısız modül: {module}.'
        super().__init__(message)


def _check_modules(modules):
    if not isinstance(modules, dict):
        raise SystemPythonError('invalid_response')
    for name in ('sysconfig', 'venv', 'ensurepip'):
        status = modules.get(name)
        if status == 'missing' and name in {'venv', 'ensurepip'}:
            raise SystemPythonError(name + '_missing')
        if status in {'failed', 'missing'}:
            raise SystemPythonError('module_failed', module=name)
        if status != 'ok':
            raise SystemPythonError('invalid_response')


def _probe_value(value):
    if not isinstance(value, dict):
        raise SystemPythonError('invalid_response')
    version = value.get('version')
    if version != [3, 11]:
        raise SystemPythonError('version', version=version)
    if value.get('bits') != 64:
        raise SystemPythonError('architecture', bits=value.get('bits'))
    if value.get('implementation') != 'cpython':
        raise SystemPythonError('implementation')
    _check_modules(value.get('modules'))
    if sys.platform == 'win32' and value.get('platform') != 'win-amd64':
        raise SystemPythonError('architecture', bits=value.get('bits'))
    if not isinstance(value.get('base'), str):
        raise SystemPythonError('base_missing')
    base = Path(value['base'])
    if not base.is_absolute() or not base.is_file():
        raise SystemPythonError('base_missing')
    return base.resolve()


def _probe(command, *, failures=None):
    values = environment({'PYTHONHOME': '', 'PYTHONPATH': '', 'PYTHONSTARTUP': '',
                          'PYTHONUSERBASE': '', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                          'PYTHON_MANAGER_AUTOMATIC_INSTALL': 'false'})
    # The legacy launcher enables install-on-demand by variable presence, even 0.
    values.pop('PYLAUNCHER_ALLOW_INSTALL', None)
    try:
        result = controlled_run([*map(str, command), '-I', '-S', '-B', '-X', 'utf8', '-c', _PROBE],
                                env=values, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS, check=False)
        if result.returncode:
            raise SystemPythonError('process_failed', returncode=result.returncode)
        if len(result.stdout) > 4096:
            raise SystemPythonError('invalid_response')
        return _probe_value(json.loads(result.stdout))
    except SystemPythonError as error:
        failure = error
    except subprocess.TimeoutExpired:
        failure = SystemPythonError('timeout')
    except OSError as error:
        failure = SystemPythonError('path_missing' if isinstance(error, FileNotFoundError) else 'start_failed', system_error=error)
    except (ValueError, TypeError, AttributeError):
        failure = SystemPythonError('invalid_response')
    if failures is not None:
        failures.append(failure)
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
    if not path.is_absolute() or not path.is_file():
        raise SystemPythonError('path_missing')
    if _excluded(path):
        raise SystemPythonError('excluded')
    failures = []
    base = _probe([path], failures=failures)
    if base is None:
        raise failures[-1] if failures else SystemPythonError('invalid_response')
    if _excluded(base):
        raise SystemPythonError('excluded')
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
        raise SystemPythonError('path_missing')
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
    failures = []
    for command in (_selected_candidates(selection) if selection else _candidates()):
        executable = Path(command[0])
        if _excluded(executable):
            failures.append(SystemPythonError('excluded'))
            continue
        # PATH aliases/case differences must not repeatedly consume a slow
        # interpreter's entire timeout budget. Keep launcher arguments distinct.
        resolved = executable.resolve()
        identity = (os.path.normcase(str(resolved)), *map(str, command[1:]))
        if identity in seen:
            continue
        seen.add(identity)
        base = _probe(command, failures=failures)
        if base is not None:
            try:
                if _excluded(base):
                    raise SystemPythonError('excluded')
                if base == resolved:
                    # This exact file has passed every probe check already.
                    return base
                return validate_python(base)
            except OperationCancelled:
                raise
            except SystemPythonError as error:
                failures.append(error)
    raise _discovery_failure(failures, selection)


def _discovery_failure(failures, selection):
    # Prefer a compatible interpreter's missing components over unrelated PATH
    # versions or stale registry/default paths; never hide the manual probe error.
    component_failure = next((error for error in failures if error.reason in {
        'venv_missing', 'ensurepip_missing', 'module_failed', 'base_missing'}), None)
    execution_failures = [error for error in failures if error.reason in {
        'start_failed', 'process_failed', 'timeout', 'invalid_response'}]
    meaningful = [error for error in failures if error.reason not in {'path_missing', 'excluded'}]
    if component_failure:
        return component_failure
    if execution_failures:
        return execution_failures[-1]
    if meaningful:
        return meaningful[-1]
    if failures:
        return failures[-1]
    return SystemPythonError('path_missing' if selection else 'not_found')
