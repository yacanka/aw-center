"""Project-local package checks and explicit installation for the desktop profiles."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from scripts.launcher import toolchain
from scripts.launcher.certificates import package_trust_environment
from scripts.launcher.installation_dependencies import capture, _pip_proxy_environment, _succeeded
from scripts.launcher.installation_permissions import require_unlinked
from scripts.launcher.installation_profiles import installation_home
from scripts.launcher.installation_sources import SourceSettings, _https_url, fetch_artifact, load_catalog
from scripts.launcher.installation_state import private_directory
from scripts.launcher.model import LauncherError, Project
from scripts.launcher.process import OperationCancelled, check_cancelled, controlled_run, environment, frontend_environment
from scripts.launcher import system_node

from .paths import worker_directory


@dataclass(frozen=True)
class ProfileProject(Project):
    environment_dir: Path

    @property
    def venv(self):
        return self.environment_dir


@dataclass(frozen=True)
class PackageDifference:
    required: str
    installed: str | None


def _base_from_config(venv):
    cfg = venv / 'pyvenv.cfg'
    if cfg.is_file() and cfg.stat().st_size < 16384:
        for line in cfg.read_text(encoding='utf-8').splitlines():
            key, _, value = line.partition('=')
            if key.strip() == 'executable':
                return Path(value.strip()).resolve()
    return None


def selected_project(values):
    root = Path(values.get('source_root') or worker_directory()).absolute()
    project = Project(root, root / 'backend/manage.py', root / 'frontend/package.json', root / 'requirements.txt')
    selection = values.get('python_command')
    profile = values.get('profile', 'dev')
    if profile not in {'dev', 'prod'}:
        raise LauncherError('Geçerli bir profil seçin.')
    if not selection:
        return project
    base = _selected_base(selection)
    # The ID distinguishes identical Python versions installed at different locations.
    key = hashlib.sha256(os.fsencode(os.path.normcase(str(base)))).hexdigest()[:16]
    venv = project.root / '.runtime' / 'venvs' / f'{profile}-{key}'
    if not venv.exists() and (not project.venv.exists() or _base_from_config(project.venv) == base):
        return project
    return ProfileProject(project.root, project.manage_py, project.package_json, project.requirements, venv)


def _selected_base(selection):
    base = Path(selection).expanduser()
    if not base.is_absolute() or not base.is_file():
        raise LauncherError('Seçilen Python bulunamadı. Kaynaklar sekmesinden kurulu bir Python seçin.')
    return base.resolve()


def _run(command, timeout=15):
    environment = {**os.environ, 'PYTHON_MANAGER_AUTOMATIC_INSTALL': 'false', 'PYTHONDONTWRITEBYTECODE': '1'}
    environment.pop('PYLAUNCHER_ALLOW_INSTALL', None)
    return controlled_run([str(part) for part in command], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', check=False, timeout=timeout,
                          stdin=subprocess.DEVNULL,
                          env=environment)


def _python_hint(executable):
    if not executable.is_file():
        return None
    script = ('import json,sys;print(json.dumps([sys.implementation.name,'
              'list(sys.version_info[:3]),getattr(sys,"_base_executable",None) or sys.executable]))')
    try:
        result = _run([executable, '-I', '-S', '-B', '-c', script])
        implementation, version, base = json.loads(result.stdout)
        base = Path(base)
        if (not result.returncode and implementation == 'cpython' and len(version) == 3
                and all(type(part) is int for part in version) and version[0] == 3 and base.is_file()):
            return tuple(version), base.resolve()
    except (ValueError, TypeError, OSError, subprocess.TimeoutExpired):
        pass
    return None


def _registry_pythons():
    import winreg
    def subkeys(key):
        for index in range(winreg.QueryInfoKey(key)[0]):
            yield winreg.EnumKey(key, index)
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Python', 0, winreg.KEY_READ | view) as companies:
                    for company in subkeys(companies):
                        with winreg.OpenKey(companies, company) as tags:
                            for tag in subkeys(tags):
                                try:
                                    with winreg.OpenKey(tags, tag + r'\InstallPath') as key:
                                        try:
                                            yield Path(winreg.QueryValueEx(key, 'ExecutablePath')[0])
                                        except OSError:
                                            yield Path(winreg.QueryValueEx(key, '')[0]) / 'python.exe'
                                except OSError:
                                    continue
            except OSError:
                continue


def _python_candidates():
    if not getattr(sys, 'frozen', False):
        yield Path(getattr(sys, '_base_executable', None) or sys.executable)
    if os.name == 'nt':
        launcher = shutil.which('py')
        if launcher:
            try:
                output = _run([launcher, '-0p'])
                for line in output.stdout.splitlines():
                    match = re.search(r'([A-Z]:[\\/].*?python(?:[0-9.]*)?\.exe)\s*$', line, re.I)
                    if match:
                        yield Path(match[1])
            except (OSError, subprocess.TimeoutExpired):
                pass
        yield from _registry_pythons()
        if local := os.environ.get('LOCALAPPDATA'):
            # Python Install Manager may have no PEP 514 registration or accessible py alias.
            for directory in (Path(local) / 'Python', Path(local) / 'Programs/Python'):
                if directory.is_dir():
                    for installation in directory.iterdir():
                        yield installation / 'python.exe'
    for directory in os.get_exec_path():
        path = Path(directory.strip('"'))
        if not path.is_absolute() or path.name.casefold() == 'windowsapps':
            continue
        for name in ('python.exe', 'python3.exe') if os.name == 'nt' else ('python3', 'python'):
            yield path / name
    if os.environ.get('LOCALAPPDATA'):
        artifact = load_catalog()['python']
        yield toolchain._directory(installation_home(), artifact) / artifact.executable


def python_choices():
    found = {}
    seen = set()
    for candidate in _python_candidates():
        check_cancelled()
        if candidate.name.casefold() == 'pythonw.exe':
            candidate = candidate.with_name('python.exe')
        if candidate in seen:
            continue
        seen.add(candidate)
        hint = _python_hint(candidate)
        if hint:
            version, base = hint
            found[base] = version
            seen.add(base)
    ordered = sorted(found.items(), key=lambda pair: (pair[1][:2] != (3, 11), pair[1], str(pair[0])))
    return [(f'Python {".".join(map(str, version))} · {path}', str(path)) for path, version in ordered]


def _managed_tool(name, node=None, *, verify=True):
    if not os.environ.get('LOCALAPPDATA'):
        return None
    artifact = load_catalog()[name]
    directory = toolchain._directory(installation_home(), artifact)
    path = directory / artifact.executable
    if not path.is_file() or not (directory / toolchain.RECEIPT).is_file():
        return None
    require_unlinked(path)
    if verify:
        if not toolchain._has_receipt(directory, artifact):
            return None
        toolchain._check_version(path, artifact.version, node=node)
    return path


def _install_tool(name, settings, *, node=None):
    home, artifact = installation_home(), load_catalog()[name]
    for directory in (home / 'cache/runtimes', home / 'runtimes'):
        private_directory(directory, root=home)
    archive = fetch_artifact(artifact, home / 'cache' / 'runtimes', settings)
    return toolchain._install(home, artifact, archive, node=node, progress=settings.progress)


def _saved_node(root):
    path = root / '.runtime/manager-node.json'
    require_unlinked(path)
    try:
        if path.stat().st_size < 16 * 1024:
            values = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(values, dict) and all(isinstance(values.get(key), str) for key in ('node', 'npm')):
                return values
    except (FileNotFoundError, UnicodeError, ValueError):
        pass
    return {}


def _pick_tool(candidates, preferred):
    """A saved preference can only select a path from current discovery candidates."""
    first = None
    for path in candidates:
        if path.is_file():
            first = first or path
            if not preferred or path == Path(preferred):
                return path
    return first


def node_environment(settings=None, *, verify=False):
    """Resolve executables directly on Run/Build. Only Resources probes or prepares them."""
    saved = {} if verify else _saved_node(worker_directory())
    node = _managed_tool('node', verify=verify)
    if node is None:
        if verify:
            try:
                node = system_node.discover_node()
            except system_node.SystemNodeError as error:
                if not settings or error.reason in {'timeout', 'start_failed', 'process_failed', 'invalid_response'}:
                    raise
        else:
            node = _pick_tool((path for path in system_node._candidates() if not system_node._excluded(path)),
                              saved.get('node'))
    if node is None and settings:
        node = _install_tool('node', settings)
    if node is None:
        raise LauncherError('Node.js eksik. Kaynaklar sekmesinden paketleri kurun veya Node 22.13+ (22.x) ya da 24+ x64 kurun.')
    npm = _managed_tool('npm', node, verify=verify)
    if npm is None:
        if verify:
            npm = system_node.find_npm_cli(node, load_catalog()['npm'].version, compatible=True)
        else:
            npm = _pick_tool(system_node._npm_candidates(node), saved.get('npm'))
    if npm is None and settings:
        npm = _install_tool('npm', settings, node=node)
    if npm is None:
        raise LauncherError('npm eksik. Kaynaklar sekmesinden paketleri kurun veya Node ile uyumlu npm 10.9.4+ (10.x) ya da 11.x kurun.')
    bin_dirs = [str(node.parent)]
    wrappers = npm.parent.parent.parent / 'bin'
    if (wrappers / 'npm.cmd').is_file():
        bin_dirs.insert(0, str(wrappers))
    return {**toolchain.MANAGED_RUNTIME_ENVIRONMENT,
            'AWCENTER_MANAGED_NODE': str(node), 'AWCENTER_MANAGED_NPM_CLI': str(npm),
            'PATH': os.pathsep.join([*bin_dirs, os.environ.get('PATH', '')])}


# Evaluate the lock with the actual target's marker environment and distribution metadata.
_PYTHON_PACKAGES = """
import json, sys, sysconfig
from importlib.metadata import distributions
from pathlib import Path
try:
    from pip._vendor.packaging.requirements import Requirement
except ImportError:
    import ensurepip
    sys.path.insert(0, str(next((Path(ensurepip.__file__).parent / '_bundled').glob('pip-*.whl'))))
    from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name
expected = sys.argv[2]
if expected and Path(sys.prefix).resolve() != Path(expected).resolve():
    sys.exit(2)
installed = {}
if expected:
    sites = {sysconfig.get_path(key) for key in ('purelib','platlib')}
    installed = {canonicalize_name(d.metadata['Name']): d.version for d in distributions(path=sites)}
missing = []
for raw in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    req = Requirement(line)
    specs = list(req.specifier)
    if req.url or req.extras or len(specs) != 1 or specs[0].operator != '==' or '*' in specs[0].version:
        sys.exit(3)
    if req.marker is not None and not req.marker.evaluate():
        continue
    actual = installed.get(canonicalize_name(req.name))
    if not actual or not req.specifier.contains(actual, prereleases=True):
        missing.append([req.name + str(req.specifier), actual])
print(json.dumps(missing))
"""


def _missing_python(project, python):
    try:
        result = _run([python, '-I', '-B', '-c', _PYTHON_PACKAGES, project.requirements,
                       str(project.venv) if project.python.is_file() else ''], timeout=60)
        missing = json.loads(result.stdout) if result.returncode == 0 else None
        if isinstance(missing, list) and all(isinstance(row, list) and len(row) == 2 and
                isinstance(row[0], str) and (row[1] is None or isinstance(row[1], str)) for row in missing):
            return [PackageDifference(*row) for row in missing]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    raise LauncherError('Python paketleri okunamadı. Seçilen Python, sanal ortam, pip/ensurepip ve requirements.txt dosyasını kontrol edin.')


def _platform_matches(selectors, value):
    return f'!{value}' not in selectors and (not any(not s.startswith('!') for s in selectors) or value in selectors)


def _missing_frontend(project, *, directory=None):
    directory = directory or project.frontend
    lock = directory / 'package-lock.json'
    absent = [path.name for path in (directory / 'package.json', lock) if not path.is_file()]
    if absent:
        raise LauncherError('Frontend dosyası eksik: ' + ', '.join(str(directory / name) for name in absent))
    try:
        packages = json.loads(lock.read_text(encoding='utf-8'))['packages']
        missing = []
        for name, package in packages.items():
            check_cancelled()
            if not name:
                continue
            parts = name.split('/')
            if (parts[0] != 'node_modules' or any(not re.fullmatch(r'[@a-zA-Z0-9._~-]+', part)
                                                   or part in {'.', '..'} for part in parts)):
                raise ValueError
            if not _platform_matches(package.get('os', []), 'win32') or not _platform_matches(package.get('cpu', []), 'x64'):
                continue
            version = package['version']
            metadata = directory.joinpath(*parts, 'package.json')
            try:
                installed = json.loads(metadata.read_text(encoding='utf-8')).get('version')
            except (FileNotFoundError, ValueError):
                installed = None
            if installed != version:
                missing.append(PackageDifference(f'{name.removeprefix("node_modules/")}@{version}', installed))
        return missing
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        raise LauncherError('Frontend paketleri okunamadı. frontend/package-lock.json dosyasını ve erişim izinlerini kontrol edin.') from None


def _resource_source(values, kind):
    mode = values.get('source_mode', 'online')
    if mode == 'offline':
        field = 'wheels_dir' if kind == 'python' else 'npm_cache_dir'
        selected = values.get(field)
        if not selected or not Path(selected).is_dir():
            label = 'wheel' if kind == 'python' else 'npm cache'
            raise LauncherError(f'Çevrimdışı kurulum için {label} klasörünü seçin.')
        if kind == 'python':
            return ['--no-index', '--only-binary=:all:', '--find-links', str(Path(selected).resolve())]
        return ['--offline', '--cache', str(Path(selected).resolve())]
    if mode not in {'online', 'corporate'}:
        raise LauncherError('Geçerli bir paket kaynağı seçin.')
    field = 'python_index_url' if kind == 'python' else 'npm_registry_url'
    public = 'https://pypi.org/simple' if kind == 'python' else 'https://registry.npmjs.org'
    url = values.get(field) if mode == 'corporate' else public
    if not url:
        raise LauncherError('Kurumsal Python indeksini seçin.' if kind == 'python' else 'Kurumsal npm deposunu seçin.')
    _https_url(url)
    if kind == 'python':
        return ['--index-url', url]
    return ['--registry', url, '--replace-registry-host=never' if mode == 'corporate' else '--replace-registry-host=always']


def _python_base(values, settings):
    if values.get('python_command'):
        return _selected_base(values['python_command'])
    choices = python_choices()
    if choices:
        return Path(choices[0][1])
    if settings:
        return _install_tool('python', settings)
    raise LauncherError('Python eksik. Kaynaklar sekmesinden kurulum yapın veya kurulu bir Python seçin.')


def _report(notify, label, missing):
    if not missing:
        notify('status', f'{label} · kilitli paketler kurulu.')
        return
    # Use a display separator that cannot be mistaken for a credential assignment.
    absent = [item.required.replace('==', ' ') for item in missing if item.installed is None]
    mismatched = [f'{item.required.replace("==", " ")} (kurulu {item.installed})'
                  for item in missing if item.installed is not None]
    for title, lines in (('Eksik', absent), ('Sürümü farklı', mismatched)):
        if lines:
            notify('status', f'{label} · {title} ({len(lines)})')
            for offset in range(0, len(lines), 12):
                notify('status', ', '.join(lines[offset:offset + 12]))


def _python_resources(project, values, settings, notify):
    if not project.requirements.is_file():
        raise LauncherError(f'Python paket listesi eksik: {project.requirements}')
    require_unlinked(project.venv)
    if project.python.is_file():
        python = project.python
    else:
        notify('status', f'Sanal ortam eksik: {project.venv}')
        python = _python_base(values, settings)
    missing = _missing_python(project, python)
    _report(notify, 'Python', missing)
    if not settings:
        return
    source = _resource_source(values, 'python') if missing else []
    if not project.python.is_file():
        if project.venv.exists() and any(project.venv.iterdir()):
            raise LauncherError('Sanal ortam eksik veya yarım. Mevcut ortamı yedekleyip kurulum işlemini yeniden deneyin.')
        project.venv.parent.mkdir(parents=True, exist_ok=True)
        _succeeded(capture([python, '-I', '-m', 'venv', project.venv], project), 'Virtual environment oluşturma')
    if missing:
        trust = nullcontext({}) if settings.mode == 'offline' else package_trust_environment({}, python=project.python)
        with trust as env:
            if settings.mode != 'offline':
                env.update(_pip_proxy_environment(project.python, project, env))
            pins = [item.required for item in missing]
            _succeeded(capture([project.python, '-m', 'pip', 'install', '--no-deps', *source, *pins],
                               project, env, progress=settings.progress), 'Python paket kurulumu', requirements=project.requirements)
        if _missing_python(project, project.python):
            raise LauncherError('Kurulumdan sonra Python paketlerinin sürümleri requirements.txt ile uyuşmuyor.')
    _succeeded(capture([project.python, '-m', 'pip', 'check'], project), 'Python bağımlılık doğrulaması')


def _frontend_resources(project, values, settings, notify):
    missing = _missing_frontend(project)
    _report(notify, 'Frontend', missing)
    source = _resource_source(values, 'npm') if settings and missing else []
    tools = node_environment(settings, verify=True)
    if not settings:
        return
    from scripts.launcher.developer_readiness import _publish
    selection = {'node': tools['AWCENTER_MANAGED_NODE'], 'npm': tools['AWCENTER_MANAGED_NPM_CLI']}
    if selection != _saved_node(project.root):
        _publish(project.root / '.runtime/manager-node.json', selection)
    if missing:
        notify('status', 'npm ci, eksik frontend paketleri için kilitli paket ağacını hazırlıyor.')
        _install_frontend(project, values, settings, tools, source)
    if values['profile'] == 'dev':
        _prepare_renderer(project, tools, notify)


def _prepare_renderer(project, tools, notify):
    notify('status', 'Local için Mermaid görüntüleyicisi hazırlanıyor.')
    script = project.frontend / 'scripts/build-mermaid-renderer.mjs'
    output = project.frontend / '.cache/mermaid/renderer.js'
    if not script.is_file():
        raise LauncherError(f'Mermaid derleme dosyası eksik: {script}')
    require_unlinked(output)
    try:
        with frontend_environment(True):
            result = controlled_run(
                [tools['AWCENTER_MANAGED_NODE'], str(script), '--dev'], cwd=project.frontend,
                env=environment(tools), check=False, capture_output=True, stdin=subprocess.DEVNULL, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        raise LauncherError('Mermaid görüntüleyicisi hazırlanamadı. Node ve frontend paketlerini kontrol edin.') from None
    if result.returncode or not output.is_file():
        raise LauncherError('Mermaid görüntüleyicisi oluşturulamadı. Frontend paketlerini ve .cache yazma iznini kontrol edin.')


def _stage_npm_lock(source, destination, registry):
    if not registry:
        shutil.copyfile(source, destination)
        return
    prefix = _https_url(registry).rstrip('/') + '/'
    lock = json.loads(source.read_text(encoding='utf-8'))
    for package in lock['packages'].values():
        resolved = package.get('resolved')
        if not resolved:
            continue
        parsed = urlsplit(_https_url(resolved))
        if resolved.startswith(prefix):
            relative = resolved[len(prefix):]
        elif parsed.hostname in {'registry.npmjs.org', 'registry.npmjs.com'}:
            relative = parsed.path.lstrip('/')
        else:
            raise LauncherError('Kilitli npm dosyasının adresi kurumsal registry altında çözülemiyor.')
        if not relative or any(part in {'', '.', '..'} for part in unquote(relative).replace('\\', '/').split('/')):
            raise LauncherError('Kilitli npm dosyasının kurumsal registry yolu geçersiz.')
        # Pacote host replacement discards registry path prefixes. Keep each full tarball URL and its lock integrity.
        package['resolved'] = prefix + relative
    destination.write_text(json.dumps(lock, ensure_ascii=False), encoding='utf-8')


def _install_frontend(project, values, settings, tools, source):
    node, npm = tools['AWCENTER_MANAGED_NODE'], tools['AWCENTER_MANAGED_NPM_CLI']
    trust = nullcontext(tools) if settings.mode == 'offline' else package_trust_environment(tools, node=node)
    # npm ci replaces its target. Complete the installation before replacing any working tree.
    runtime_dir = project.root / '.runtime'
    require_unlinked(runtime_dir)
    runtime_dir.mkdir(exist_ok=True)
    output = project.frontend / 'node_modules'
    require_unlinked(output)
    with tempfile.TemporaryDirectory(prefix='npm-setup-', dir=runtime_dir) as staging, trust as env:
        stage = Path(staging)
        shutil.copyfile(project.package_json, stage / 'package.json')
        _stage_npm_lock(project.frontend / 'package-lock.json', stage / 'package-lock.json',
                        values.get('npm_registry_url') if settings.mode == 'corporate' else None)
        if settings.mode == 'offline':
            # npm writes indexes and diagnostics even in offline mode. Keep the supplied media read-only.
            contents = Path(values['npm_cache_dir']).resolve() / '_cacache'
            if not contents.is_dir():
                raise LauncherError('Seçilen npm cache klasöründe _cacache bulunamadı.')
            cache = stage / 'npm-cache'
            shutil.copytree(contents, cache / '_cacache')
            source = ['--offline', '--cache', cache]
        with frontend_environment(True):
            _succeeded(capture([node, npm, 'ci', '--prefix', stage, '--include=dev', '--include=optional',
                                '--no-audit', '--no-fund', *source],
                               project, env), 'Frontend paket kurulumu')
        if _missing_frontend(project, directory=stage):
            raise LauncherError('Hazırlanan frontend paketlerinin sürümleri package-lock.json ile uyuşmuyor.')
        saved = None
        if output.exists():
            # Keep the original outside the temporary tree until the replacement is published.
            backup_dir = runtime_dir / 'npm-backups'
            require_unlinked(backup_dir)
            backup_dir.mkdir(exist_ok=True)
            saved = Path(tempfile.mkdtemp(prefix='preserved-', dir=backup_dir)) / 'node_modules'
            output.replace(saved)
        try:
            (stage / 'node_modules').replace(output)
        except OSError:
            if saved and saved.exists() and not output.exists():
                saved.replace(output)
            raise


def execute(action, values, notify, ask=None):
    if action not in {'check', 'install'}:
        raise LauncherError('Geçersiz kaynak işlemi.')
    project = selected_project(values)
    settings = None
    if action == 'install':
        directory = Path(sys.executable).parent if getattr(sys, 'frozen', False) else project.root
        settings = SourceSettings(mode=values.get('source_mode', 'online'),
                                  runtime_dirs=(directory, project.root.parent),
                                  progress=lambda message: notify('status', message))
        if settings.mode == 'restricted':
            raise LauncherError('Çevrimiçi, kurumsal veya çevrimdışı kaynak seçin.')
    errors = []
    # The worker holds the profile/source/runtime leases for the entire operation.
    for step in (_python_resources, _frontend_resources):
        check_cancelled()
        try:
            step(project, values, settings, notify)
        except OperationCancelled:
            raise
        except LauncherError as exc:
            errors.append(str(exc))
            notify('status', str(exc))
    if errors:
        raise LauncherError(' '.join(errors))
    notify('status', 'Paket kurulumu tamamlandı.' if settings else 'Paket kontrolü tamamlandı.')
