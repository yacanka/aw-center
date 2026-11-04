"""Platform-bound Windows installation bundles without private state.

The root manifest supplements, rather than changes, the dependency cache's v1
manifest. Version 2 may replace runtime archives with explicit host requirements.
Verification is read-only and must precede installation mutations.
"""
from __future__ import annotations

import json
import hashlib
import sys
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile

from .model import LauncherError, Project, Scope
from .offline_manifest import (artifact_metadata, ensure_wheels_only, file_sha256,
                               lock_metadata, target_metadata, verify_offline_manifest)
from .packaging import EXCLUDED_NAMES, EXCLUDED_PARTS, EXCLUDED_SUFFIXES

INSTALL_MANIFEST = 'install-manifest.json'
ASSET_MANIFEST = 'asset-manifest.json'
CORE_ARTIFACTS = ('python', 'node', 'npm')
OPTIONAL_ARTIFACTS = ('ffmpeg', 'libreoffice', 'poppler')
SOURCE_EXCLUSIONS = EXCLUDED_PARTS | {
    '.agents', '.codex', '.aws', '.pytest_cache', '.ruff_cache', 'test-results',
    'playwright-report', 'static', 'release-evidence', 'offline', 'private_media',
    'private', 'config', 'configs', 'certificates', '.playwright-cli', '.superpowers',
    'output',
}
PACKAGE_MANAGER_PRIVATE_FILES = {'.npmrc', '.pypirc', '.netrc', '_netrc'}
EXTRACTED_JSON_FILES = {
    'package.json', 'package-lock.json', 'frontend/package.json',
    'frontend/package-lock.json', 'frontend/tsconfig.json', 'frontend/tsconfig.app.json',
    'backend/integrations/assistant/guide_data.json',
    'scripts/launcher/installation_catalog.json',
}
EXTRACTED_ROOT_FILES = {
    '.dockerignore', '.env.example', '.gitattributes', '.gitignore', 'AGENTS.md',
    'README.md', 'AWCenter.cmd', 'docker-compose.yml', 'launcher.py',
    'package.json', 'package-lock.json', 'requirements.in', 'requirements.txt',
}
EXTRACTED_ROOT_DIRECTORIES = {'backend', 'frontend', 'scripts', 'deploy', 'docs', '.github'}
EXTRACTED_SUFFIXES = {
    '.py', '.ts', '.js', '.mjs', '.cjs', '.json', '.md', '.vue', '.html', '.css',
    '.scss', '.txt', '.in', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.cmd', '.bat',
    '.sh', '.conf', '.svg', '.png', '.jpg', '.jpeg', '.ico', '.webmanifest', '.example', '.sha256',
}
# The live production template may contain institution-specific values. Bundles
# deliberately regenerate a template and never copy that file from a checkout.
PRODUCTION_SAMPLE = '''# Generated installation sample; provision supplies private values externally.
AWCENTER_DEPLOYMENT_MODE=windows-native
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=
CSRF_TRUSTED_ORIGINS=
DATABASE_URL=
DATABASE_CONN_MAX_AGE=0
PRIVATE_MEDIA_ROOT=
DOORS_ENABLED=False
JIRA_ENABLED=False
TEAMCENTER_ENABLED=False
DOCPROOF_ENABLED=False
NUMARATOR_ENABLED=False
'''


class BundleHostRuntimeError(LauncherError):
    """An offline prerequisite failure with fixed labels and no private paths."""

    def __init__(self, artifact: str):
        labels = {'python': 'Python', 'node': 'Node.js', 'npm': 'npm'}
        self.code = 'bundle_host_runtime_missing'
        self.artifact = artifact if artifact in labels else None
        self.remedy = {
            'python': 'Bu çevrimdışı paket için tam CPython 3.11 x64 kurulumunu seçin; venv ve ensurepip desteği gerekir.',
            'node': 'Bu çevrimdışı paket için kurulu Node 22.12+ (22.x) veya 24+ x64 yürütülebilir dosyasını seçin.',
            'npm': 'Bu çevrimdışı paket için seçilen uyumlu Node kurulumunun yanında npm 10.9.4+ (10.x) veya 11.x bulunmalıdır.',
        }.get(self.artifact, 'Bu çevrimdışı paketin gerekli sistem araçlarını kurup yeniden seçin.')
        super().__init__(f"Çevrimdışı paketin gerektirdiği {labels.get(self.artifact, 'sistem aracı')} bulunamadı veya uyumsuz.")


def _json_object(path: Path, limit: int = 16 * 1024 * 1024) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        if path.stat().st_size > limit:
            raise ValueError('oversized JSON')
        value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError('JSON object required')
        return value
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise LauncherError('installation manifest is unavailable or invalid') from error


def _relative_path(value: str) -> Path:
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise LauncherError('installation artifact path is unsafe')
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise LauncherError('installation artifact path is unsafe')
    if any(part in {'.', '..'} or part.endswith((' ', '.')) or
           any(ord(character) < 32 for character in part) for part in path.parts):
        raise LauncherError('installation artifact path is unsafe')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}
    if any(part.split('.')[0].upper() in reserved for part in path.parts):
        raise LauncherError('installation artifact path is unsafe')
    return Path(*path.parts)


def _safe_path(root: Path, path: Path) -> Path:
    """Check directories as well as files, including Windows junctions."""
    root = root.absolute()
    path = path.absolute()
    if not path.is_relative_to(root):
        raise LauncherError('installation artifact escaped its root')
    current = root
    for part in ('', *path.relative_to(root).parts):
        current = current / part
        try:
            info = current.lstat()
        except OSError as error:
            raise LauncherError('installation artifact is unavailable') from error
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise LauncherError('installation artifacts cannot contain links or reparse points')
    if not path.resolve().is_relative_to(root.resolve()):
        raise LauncherError('installation artifact escaped its root')
    return path


def _source_packageable(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    unsafe_env = path.name.startswith('.env') and not path.name.endswith(('.example', '.sample'))
    return (path.is_file() and not unsafe_env and path.name not in EXCLUDED_NAMES and
            path.name not in PACKAGE_MANAGER_PRIVATE_FILES and
            path.suffix.lower() not in EXCLUDED_SUFFIXES and
            not set(relative.parts).intersection(SOURCE_EXCLUSIONS))


def install_inventory(directory: Path, *, exclude: tuple[str, ...] = (), source_state: bool = False) -> list[dict]:
    """Hash every regular file and reject special files, links and junctions."""
    directory = Path(directory).absolute()
    _safe_path(directory, directory)
    artifacts = []
    for current, directories, files in os.walk(directory, followlinks=False):
        in_source = source_state and Path(current).relative_to(directory).parts[:1] == ('source',)
        if in_source:
            directories[:] = [name for name in directories if name not in SOURCE_EXCLUSIONS]
        for name in directories:
            _safe_path(directory, Path(current) / name)
        for name in files:
            candidate = Path(current) / name
            if in_source and not _source_packageable(candidate, directory / 'source'):
                continue
            path = _safe_path(directory, candidate)
            relative = path.relative_to(directory).as_posix()
            _relative_path(relative)
            if not path.is_file():
                raise LauncherError('installation artifacts must be regular files')
            if relative not in exclude:
                artifacts.append({'path': relative, 'sha256': file_sha256(path),
                                  'size': path.stat().st_size})
    return sorted(artifacts, key=lambda item: item['path'])


def _verify_inventory(root: Path, expected, *, exclude: tuple[str, ...], source_state: bool = False) -> None:
    if not isinstance(expected, list):
        raise LauncherError('installation checksum manifest is invalid')
    names = set()
    for entry in expected:
        if not isinstance(entry, dict) or set(entry) != {'path', 'size', 'sha256'}:
            raise LauncherError('installation checksum manifest is invalid')
        _relative_path(entry['path'])
        if entry['path'].casefold() in names:
            raise LauncherError('duplicate installation artifact path')
        names.add(entry['path'].casefold())
        if (type(entry['size']) is not int or entry['size'] < 0 or
                not isinstance(entry['sha256'], str) or
                re.fullmatch(r'[0-9a-f]{64}', entry['sha256']) is None):
            raise LauncherError('installation checksum manifest is invalid')
    actual = install_inventory(root, exclude=exclude, source_state=source_state)
    if sorted(expected, key=lambda item: item['path']) != actual:
        raise LauncherError('installation artifact checksum verification failed')


def verify_asset_source(directory: Path) -> dict:
    """Validate an explicitly supplied, immutable, approved private asset set.

    Only ai-models/ and DOCX document-templates/ files are transferable. Private
    integration JSON and credentials never belong in a distributable bundle.
    """
    directory = Path(directory).absolute()
    manifest_path = _safe_path(directory, directory / ASSET_MANIFEST)
    manifest = _json_object(manifest_path)
    identifier = manifest.get('asset_set')
    if (manifest.get('format_version') != 1 or not isinstance(identifier, str) or
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', identifier) is None or
            identifier in {'.', '..'}):
        raise LauncherError('approved asset-set identifier or version is invalid')
    expected = manifest.get('artifacts')
    if not isinstance(expected, list) or not expected:
        raise LauncherError('approved asset set is empty')
    for entry in expected:
        relative = _relative_path(entry.get('path') if isinstance(entry, dict) else None)
        if len(relative.parts) < 2 or relative.parts[0] not in {'ai-models', 'document-templates'}:
            raise LauncherError('asset set contains an unsupported artifact')
        if relative.parts[0] == 'document-templates' and relative.suffix.lower() != '.docx':
            raise LauncherError('only approved DOCX templates may be imported')
    _verify_inventory(directory, expected, exclude=(ASSET_MANIFEST,))
    return manifest


def _source_files(project: Project) -> list[Path]:
    root = project.root.absolute()
    _safe_path(root, root)
    selected = []
    checkout = (root / '.git').exists() and shutil.which('git') is not None
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name not in SOURCE_EXCLUSIONS]
        if not checkout and Path(current) == root:
            directories[:] = [name for name in directories if name in EXTRACTED_ROOT_DIRECTORIES]
        for name in directories:
            _safe_path(root, Path(current) / name)
        for name in files:
            path = Path(current) / name
            if (not _source_packageable(path, root) or
                    path.suffix.lower() in {'.crt', '.cer', '.der'}):
                continue
            relative = path.relative_to(root).as_posix()
            if not checkout and ((path.parent == root and name not in EXTRACTED_ROOT_FILES) or
                    (path.suffix.lower() == '.json' and relative not in EXTRACTED_JSON_FILES) or
                    (path.suffix and path.suffix.lower() not in EXTRACTED_SUFFIXES)):
                continue
            _safe_path(root, path)
            selected.append(path)
    if checkout:
        completed = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                                   check=False, capture_output=True)
        if completed.returncode:
            raise LauncherError('safe tracked source inventory requires Git in a checkout')
        tracked = set(completed.stdout.decode('utf-8').split('\0'))
        selected = [path for path in selected if path.relative_to(root).as_posix() in tracked or
                    path.relative_to(root).as_posix().startswith('scripts/launcher/') or
                    path.name in {'AWCenter.cmd', 'installation-catalog.json'}]
    return sorted(selected)


def copy_install_source(project: Project, destination: Path) -> None:
    """Copy source from a checkout or an extracted release without local secrets."""
    files = _source_files(project)  # Validate every input before creating output.
    if destination.exists():
        raise LauncherError('installation source destination must not exist')
    destination.mkdir(parents=True)
    for source in files:
        target = destination / source.relative_to(project.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (destination / 'backend').mkdir(exist_ok=True)
    (destination / 'backend/.env.production.sample').write_text(PRODUCTION_SAMPLE, encoding='utf-8')


def _require_windows_target() -> dict:
    target = target_metadata()
    if (target.get('system') != 'windows' or target.get('machine') not in {'amd64', 'x86_64'} or
            target.get('python') != '3.11' or target.get('implementation') != 'cpython'):
        raise LauncherError('prepare-install-bundle requires Windows x64 and CPython 3.11; dependencies are target-specific')
    return target


def _catalog():
    from .installation_sources import load_catalog
    catalog = load_catalog()
    if any(name not in catalog for name in CORE_ARTIFACTS):
        raise LauncherError('reviewed Python, Node and npm artifacts are required')
    return catalog


def _runtime_metadata(catalog: dict) -> dict:
    return {name: {'version': catalog[name].version, 'filename': catalog[name].filename,
                   'sha256': catalog[name].sha256} for name in sorted(catalog)
            if name in (*CORE_ARTIFACTS, *OPTIONAL_ARTIFACTS)}


def _external_runtime_names(value) -> frozenset[str]:
    if (not isinstance(value, (set, frozenset)) or
            any(not isinstance(name, str) or name not in CORE_ARTIFACTS for name in value)):
        raise LauncherError('external runtimes may contain only Python, Node and npm')
    return frozenset(value)


def _supported_host_version(name: str, value) -> bool:
    # Versions cross the distribution boundary; never accept executable paths,
    # prereleases or arbitrary subprocess output as host requirements.
    if not isinstance(value, str) or len(value) > 32:
        return False
    if name == 'python':
        return re.fullmatch(r'3\.11\.(0|[1-9][0-9]*)', value) is not None
    if name == 'npm':
        from .system_node import supported_npm_version
        return supported_npm_version(value)
    match = re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value)
    if match is None:
        return False
    major, minor, _ = map(int, match.groups())
    return (major == 22 and minor >= 13) or major >= 24


def _host_runtime_metadata(toolchain, names: frozenset[str]) -> dict[str, str]:
    if not isinstance(toolchain, dict):
        raise LauncherError('installation bundle toolchain metadata is invalid')
    hosts = {name: toolchain.get(name) for name in sorted(names)}
    if any(not _supported_host_version(name, version) for name, version in hosts.items()):
        raise LauncherError('installation host runtimes require Python 3.11, supported Node and supported npm')
    return hosts


def _bundle_host_runtimes(manifest: dict) -> dict[str, str]:
    if manifest['format_version'] == 1:
        if 'host_runtimes' in manifest:
            raise LauncherError('complete installation bundles cannot declare host runtimes')
        return {}
    hosts = manifest.get('host_runtimes')
    if (not isinstance(hosts, dict) or not hosts or
            any(name not in CORE_ARTIFACTS for name in hosts) or
            any(not _supported_host_version(name, version) for name, version in hosts.items())):
        raise LauncherError('installation host runtime requirements are invalid')
    return hosts


def _verify_dependency_toolchain(toolchain, catalog: dict, hosts: dict, version: int) -> None:
    if not isinstance(toolchain, dict):
        raise LauncherError('installation bundle toolchain metadata is invalid')
    for name in CORE_ARTIFACTS:
        actual = toolchain.get(name)
        if name in hosts:
            if actual != hosts[name]:
                raise LauncherError('installation host runtime versions differ from the dependency toolchain')
            continue
        if name == 'python' and version == 1:
            # Complete v1 bundles historically allow another CPython 3.11 patch
            # version to prepare their wheels; preserve that existing contract.
            continue
        normalized = actual.removeprefix('v') if name == 'node' and isinstance(actual, str) else actual
        if normalized != catalog[name].version:
            raise LauncherError('offline dependencies were prepared with a different included runtime')


def source_provenance(project: Project) -> str:
    """Use a real commit when available, otherwise fingerprint distributed source."""
    if (project.root / '.git').exists() and shutil.which('git'):
        try:
            result = subprocess.run(['git', '-C', str(project.root), 'rev-parse', 'HEAD'],
                                    capture_output=True, text=True, check=False, timeout=10)
            if result.returncode == 0 and re.fullmatch(r'[0-9a-f]{40,64}', result.stdout.strip()):
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    digest = hashlib.sha256()
    for path in _source_files(project):
        digest.update((path.relative_to(project.root).as_posix() + '\0' + file_sha256(path) + '\n').encode('utf-8'))
    return 'source-sha256:' + digest.hexdigest()


def _validate_bootstrap(project: Project) -> None:
    files = {path.relative_to(project.root).as_posix() for path in _source_files(project)}
    required = {'AWCenter.cmd', 'launcher.py', 'backend/manage.py', 'requirements.txt',
                'frontend/package.json', 'frontend/package-lock.json',
                'scripts/launcher/installation_sources.py',
                'scripts/launcher/installation_catalog.json',
                'scripts/launcher/installation_python.sha256',
                'scripts/launcher/installation_python_startup.sha256',
                'scripts/launcher/installation_verify_python.py'}
    if not required.issubset(files):
        raise LauncherError('installation bundle source is incomplete; bootstrap and dependency locks are required')


def _capture(command: list, project: Project, overrides: dict):
    from .installation_dependencies import capture
    try:
        return capture(command, project, overrides)
    except OSError:
        raise LauncherError('package tool could not run; verify the managed toolchain') from None


def _require_success(result, stage: str) -> None:
    if result.returncode:
        raise LauncherError(stage + ' failed; package-manager diagnostics were withheld to protect credentials')


def _offline_source(project: Project, settings) -> Path | None:
    # Selection validates target, locks and every v1 artifact before any copy.
    from .installation_dependencies import _offline_dependencies
    selected = _offline_dependencies(project, settings)
    if selected is not None:
        for current, directories, files in os.walk(selected, followlinks=False):
            for name in (*directories, *files):
                _safe_path(selected, Path(current) / name)
    return selected


def _npm_argv() -> list[str]:
    from .process import required_tool
    node = os.environ.get('AWCENTER_MANAGED_NODE')
    selected_cli = os.environ.get('AWCENTER_MANAGED_NPM_CLI')
    if node and selected_cli and Path(selected_cli).is_file():
        return [node, selected_cli]
    npm = Path(required_tool('npm'))
    cli = Path(os.environ['AWCENTER_MANAGED_NPM_CLI']) if os.environ.get('AWCENTER_MANAGED_NPM_CLI') else npm.parent.parent / 'package/bin/npm-cli.js'
    if os.name == 'nt' and node and cli.is_file():
        return [node, str(cli)]
    return [str(npm)]


def _patch_requirements(project: Project, python: str, destination: Path, overrides: dict) -> Path:
    """Acquire the lock's union for 3.11 patches, using the target pip's parser.

    The original lock remains the installation authority. A newer producer must
    also carry pins such as async-timeout required only by an older 3.11 target.
    Evaluate boundaries mentioned by markers instead of guessing a last patch.
    Platform markers still use the native producer, which must be Windows x64.
    """
    script = r'''
import re, sys
from pathlib import Path
from pip._vendor.packaging.markers import default_environment
from pip._vendor.packaging.requirements import Requirement
text = Path(sys.argv[1]).read_text(encoding="utf-8")
base = default_environment()
if base["python_version"] != "3.11":
    raise ValueError("CPython 3.11 is required")
patches = {0, int(base["python_full_version"].split(".")[2])}
for match in re.finditer(r"(?<![0-9])3\.11\.([0-9]+)(?![0-9])", text):
    patch = int(match.group(1))
    patches.update((max(0, patch - 1), patch, patch + 1))
environments = [dict(base, python_full_version=f"3.11.{patch}",
                     implementation_version=f"3.11.{patch}") for patch in patches]
for line in text.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    requirement = Requirement(line)
    if requirement.marker is None or any(requirement.marker.evaluate(env) for env in environments):
        requirement.marker = None
        print(requirement)
'''
    result = _capture([python, '-c', script, project.requirements], project, overrides)
    _require_success(result, 'CPython 3.11 patch requirement inspection')
    if not result.stdout.strip() or len(result.stdout) > 2 * 1024 * 1024:
        raise LauncherError('CPython 3.11 patch requirements could not be inspected')
    destination.write_text(result.stdout, encoding='utf-8')
    return destination


def _acquire_wheels(project: Project, destination: Path, settings, overrides: dict) -> None:
    from .installation_dependencies import availability_failure
    from .installation_sources import acquisition_urls
    python = os.environ.get('AWCENTER_MANAGED_PYTHON', sys.executable)
    indexes = acquisition_urls(settings, 'https://pypi.org/simple', settings.python_index_url)
    with tempfile.TemporaryDirectory(prefix='awcenter-wheel-acquire-') as temporary:
        requirements = project.requirements
        if 'python_full_version' in requirements.read_text(encoding='utf-8'):
            requirements = _patch_requirements(project, python, Path(temporary) / 'requirements.txt', overrides)
        offline = _offline_source(project, settings) if settings.mode in {'restricted', 'offline'} else None
        selected = offline / 'wheels' if offline else None
        for index, url in enumerate(indexes if selected is None else []):
            attempt = Path(temporary) / str(index)
            attempt.mkdir()
            result = _capture([python, '-m', 'pip', 'wheel', '--wheel-dir', attempt,
                               '--index-url', url, '-r', requirements], project, overrides)
            if not result.returncode:
                selected = attempt
                break
            if not availability_failure((result.stdout or '') + (result.stderr or ''), restricted=settings.mode == 'restricted'):
                _require_success(result, 'Python wheel acquisition')
            settings.report('Python paket kaynağı erişilemiyor; sıradaki izinli kaynak deneniyor')
        if selected is None:
            offline = _offline_source(project, settings)
            if offline is None:
                raise LauncherError('locked Python wheels are unavailable from public, selected and offline sources')
            selected = offline / 'wheels'
        ensure_wheels_only(selected)
        _require_success(_capture([python, '-m', 'pip', 'install', '--dry-run', '--ignore-installed',
                                   '--no-index', '--find-links', selected, '-r', requirements],
                                  project, overrides), 'Offline Python wheel resolution')
        shutil.copytree(selected, destination)


def _acquire_npm(project: Project, destination: Path, settings, overrides: dict) -> None:
    from .installation_dependencies import availability_failure
    from .installation_sources import acquisition_urls
    registries = acquisition_urls(settings, 'https://registry.npmjs.org', settings.npm_registry_url)
    npm = _npm_argv()
    with tempfile.TemporaryDirectory(prefix='awcenter-npm-acquire-') as temporary:
        offline = _offline_source(project, settings) if settings.mode in {'restricted', 'offline'} else None
        selected = offline / 'npm-cache' if offline else None
        for index, registry in enumerate(registries if selected is None else []):
            stage = Path(temporary) / str(index)
            stage.mkdir()
            for name in ('package.json', 'package-lock.json'):
                shutil.copyfile(project.frontend / name, stage / name)
            cache = stage / 'cache'
            isolated = Project(stage, stage / 'manage.py', stage / 'package.json', project.requirements)
            result = _capture([*npm, 'ci', '--ignore-scripts', '--cache', cache,
                               '--registry', registry, '--replace-registry-host=npmjs',
                               '--no-audit', '--no-fund'], isolated, overrides)
            if not result.returncode:
                selected = cache
                break
            if not availability_failure((result.stdout or '') + (result.stderr or ''), restricted=settings.mode == 'restricted'):
                _require_success(result, 'npm cache acquisition')
            settings.report('npm kaynağı erişilemiyor; sıradaki izinli kaynak deneniyor')
        if selected is None:
            offline = _offline_source(project, settings)
            if offline is None:
                raise LauncherError('locked npm packages are unavailable from public, selected and offline sources')
            selected = offline / 'npm-cache'
        # Only content-addressed package cache is distributable: npm logs and
        # user/global configuration may contain proxy or registry credentials.
        if not (selected / '_cacache').is_dir():
            raise LauncherError('npm content-addressed cache is incomplete')
        destination.mkdir()
        shutil.copytree(selected / '_cacache', destination / '_cacache')


def _dependency_toolchain(project: Project, overrides: dict) -> dict:
    from .process import required_tool
    python = os.environ.get('AWCENTER_MANAGED_PYTHON', sys.executable)
    commands = {'python': [python, '--version'], 'pip': [python, '-m', 'pip', '--version'],
                'node': [required_tool('node'), '--version'], 'npm': [*_npm_argv(), '--version']}
    versions = {}
    for name, command in commands.items():
        result = _capture(command, project, overrides)
        _require_success(result, 'Dependency toolchain inspection')
        parts = result.stdout.strip().split()
        versions[name] = parts[1] if name in {'python', 'pip'} and len(parts) >= 2 else result.stdout.strip()
    return versions


def _prepare_dependencies(project: Project, directory: Path, settings) -> None:
    """Acquire complete caches without Git, workspace installs or raw diagnostics."""
    from .certificates import package_trust_environment
    from .process import required_tool
    overrides = {key: os.environ[key] for key in ('PATH', 'AWCENTER_MANAGED_PYTHON', 'AWCENTER_MANAGED_NODE', 'AWCENTER_MANAGED_NPM_CLI') if key in os.environ}
    overrides.update(NODE_TLS_REJECT_UNAUTHORIZED='1', NPM_CONFIG_STRICT_SSL='true',
                     PIP_NO_CACHE_DIR='1')
    with package_trust_environment(overrides, ca_file=settings.ca_file,
                                   python=overrides.get('AWCENTER_MANAGED_PYTHON', sys.executable),
                                   node=overrides.get('AWCENTER_MANAGED_NODE') or required_tool('node')) as trusted_env:
        directory.mkdir(parents=True)
        _acquire_wheels(project, directory / 'wheels', settings, trusted_env)
        _acquire_npm(project, directory / 'npm-cache', settings, trusted_env)
        _verify_npm_offline(project, directory / 'npm-cache', trusted_env)
        manifest = {'format_version': 1, 'commit': source_provenance(project),
                    'target': target_metadata(), 'toolchain': _dependency_toolchain(project, trusted_env),
                    'locks': lock_metadata(project, Scope()), 'artifacts': artifact_metadata(directory)}
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    verify_offline_manifest(project, Scope(), directory)


def _verify_npm_offline(project: Project, cache: Path, environment: dict) -> None:
    """Run lifecycle scripts and a build using only the prepared npm cache.

    Cache population alone uses --ignore-scripts and cannot prove native optional
    packages or postinstall outputs exist. An isolated offline build closes that gap.
    """
    npm = _npm_argv()
    with tempfile.TemporaryDirectory(prefix='awcenter-offline-smoke-') as temporary:
        staging = Path(temporary) / 'frontend'
        smoke_cache = Path(temporary) / 'npm-cache'
        shutil.copytree(cache, smoke_cache)
        shutil.copytree(project.frontend, staging,
                        ignore=shutil.ignore_patterns('node_modules', 'dist', 'test-results',
                                                     'playwright-report', '.env*', '.npmrc'))
        isolated = Project(staging, staging / 'manage.py', staging / 'package.json', None)
        for command in ([*npm, 'ci', '--offline', '--cache', str(smoke_cache), '--no-audit', '--no-fund'],
                        [*npm, 'run', 'build']):
            result = _capture(command, isolated, {**environment, 'NPM_CONFIG_OFFLINE': 'true'})
            _require_success(result, 'Offline npm lifecycle/build smoke')


def prepare_install_bundle(project: Project, output: Path, settings, assets=None, *,
                           feature_catalog=None, external_runtimes=frozenset(), manager_distribution=None) -> Path:
    """Build a transferable bundle, optionally requiring named tools on its target.

    External runtime archives are never acquired. Their producer versions, without
    executable paths, become version 2 host requirements. The default remains a
    complete version 1 bundle.
    """
    target = _require_windows_target()
    external_runtimes = _external_runtime_names(external_runtimes)
    if manager_distribution is not None and external_runtimes:
        raise LauncherError('Tam Manager paketi hedefte kurulu araç gerektiremez.')
    _validate_bootstrap(project)
    output = Path(output).expanduser().absolute()
    from .installation_permissions import require_unlinked
    require_unlinked(output)
    if output.exists() or output.is_relative_to(project.root.absolute()):
        raise LauncherError('installation bundle output must be new and outside the source tree')
    approved = verify_asset_source(Path(assets)) if assets is not None else None
    from .installation_features import read_feature_catalog
    approved_features = read_feature_catalog(Path(feature_catalog)) if feature_catalog is not None else {}
    catalog = {**_catalog(), **approved_features}
    # All preflight validation precedes output creation. Staging avoids publishing
    # a partial bundle if downloads or dependency resolution fail.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.awcenter-bundle-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'bundle'
        staging.mkdir()
        if manager_distribution is None:
            copy_install_source(project, staging / 'source')
        else:
            from scripts.manager.payload import prepare_source_payload
            from scripts.manager.distribution import copy_manager
            prepare_source_payload(project, staging / 'source')
            copy_manager(Path(manager_distribution), staging)
        from .installation_sources import fetch_artifact
        runtimes = staging / 'runtimes'
        included_runtimes = {name: metadata for name, metadata in _runtime_metadata(catalog).items()
                             if name not in external_runtimes}
        for name in included_runtimes:
            fetch_artifact(catalog[name], runtimes, settings)
        if feature_catalog is not None:
            from .installation_permissions import secure_path
            shutil.copy2(feature_catalog, staging / 'feature-catalog.json')
            secure_path(staging / 'feature-catalog.json')
        _prepare_dependencies(project, staging / 'dependencies', settings)
        if approved is not None:
            shutil.copytree(assets, staging / 'assets' / approved['asset_set'])
        toolchain = _json_object(staging / 'dependencies/manifest.json').get('toolchain')
        host_runtimes = _host_runtime_metadata(toolchain, external_runtimes)
        manifest = {'format_version': 2 if external_runtimes else 1, 'target': target,
                    'locks': lock_metadata(project, Scope()), 'runtimes': included_runtimes,
                    'toolchain': toolchain,
                    'feature_catalog': 'feature-catalog.json' if feature_catalog is not None else None,
                    'asset_set': approved['asset_set'] if approved else None,
                    'artifacts': install_inventory(staging, source_state=True)}
        if external_runtimes:
            manifest['host_runtimes'] = host_runtimes
        if manager_distribution is not None:
            manifest['manager_manifest'] = 'manager-manifest.json'
        (staging / INSTALL_MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        if manager_distribution is not None:
            from scripts.manager.distribution import seal_distribution
            seal_distribution(staging, complete=True)
        verify_install_bundle(project, staging)
        staging.rename(output)
    return output


def verify_install_bundle(project: Project, directory: Path) -> dict:
    """Verify all files, platform, locked dependencies and pinned runtimes read-only."""
    directory = Path(directory).expanduser().absolute()
    manifest = _json_object(_safe_path(directory, directory / INSTALL_MANIFEST))
    if type(manifest.get('format_version')) is not int or manifest['format_version'] not in {1, 2}:
        raise LauncherError('installation bundle manifest version is unsupported')
    host_runtimes = _bundle_host_runtimes(manifest)
    if manifest.get('target') != _require_windows_target():
        raise LauncherError('installation bundle targets a different OS, architecture or Python')
    if manifest.get('locks') != lock_metadata(project, Scope()):
        raise LauncherError('installation bundle does not match the current dependency locks')
    excluded = (INSTALL_MANIFEST,)
    if 'manager_manifest' in manifest:
        if manifest['manager_manifest'] != 'manager-manifest.json':
            raise LauncherError('Manager manifest reference is invalid')
        from scripts.manager.distribution import verify_distribution
        manager = verify_distribution(directory)
        if manager.get('complete') is not True or host_runtimes:
            raise LauncherError('Complete Manager distribution is required')
        excluded += ('manager-manifest.json',)
    _verify_inventory(directory, manifest.get('artifacts'), exclude=excluded, source_state=True)
    catalog = dict(_catalog())
    if manifest.get('feature_catalog') is not None:
        if manifest['feature_catalog'] != 'feature-catalog.json':
            raise LauncherError('installation optional feature catalog reference is invalid')
        from .installation_features import read_feature_catalog
        catalog.update(read_feature_catalog(directory / 'feature-catalog.json', require_owner=False))
    included_runtimes = {name: metadata for name, metadata in _runtime_metadata(catalog).items()
                         if name not in host_runtimes}
    if manifest.get('runtimes') != included_runtimes:
        raise LauncherError('installation bundle runtimes differ from the reviewed catalog')
    if any((directory / 'runtimes' / _relative_path(catalog[name].filename)).exists()
           for name in host_runtimes):
        raise LauncherError('installation host runtimes cannot include runtime archives')
    for name in included_runtimes:
        artifact = catalog[name]
        path = _safe_path(directory, directory / 'runtimes' / _relative_path(artifact.filename))
        try:
            digest = file_sha256(path)
        except OSError:
            raise LauncherError('installation runtime artifact is unavailable') from None
        if digest != artifact.sha256:
            raise LauncherError('installation runtime checksum verification failed')
    source = directory / 'source'
    source_project = Project(source, source / 'backend/manage.py', source / 'frontend/package.json', source / 'requirements.txt')
    if lock_metadata(source_project, Scope()) != manifest['locks']:
        raise LauncherError('bundled source dependency locks differ from the manifest')
    dependencies = verify_offline_manifest(project, Scope(), directory / 'dependencies')
    if manifest.get('toolchain') != dependencies.get('toolchain'):
        raise LauncherError('installation bundle toolchain metadata is inconsistent')
    _verify_dependency_toolchain(dependencies.get('toolchain'), catalog, host_runtimes,
                                 manifest['format_version'])
    if manifest.get('asset_set') is not None:
        asset_path = directory / 'assets' / _relative_path(manifest['asset_set'])
        if verify_asset_source(asset_path)['asset_set'] != manifest['asset_set']:
            raise LauncherError('bundled asset set identifier is inconsistent')
    return manifest


def require_bundle_host_runtimes(project: Project, settings, *,
                                python_executable: Path | None = None,
                                node_executable: Path | None = None) -> None:
    """Require selected system tools before an offline v2 bundle can be installed.

    Producer versions document dependency provenance; target tools need only meet
    the supported runtime constraints. This check never acquires artifacts.
    """
    if settings.mode != 'offline':
        return
    roots = []
    if settings.repository and '://' not in str(settings.repository):
        roots.append(Path(settings.repository))
    if settings.offline_dir:
        roots.append(Path(settings.offline_dir))
    for root in roots:
        if (root / INSTALL_MANIFEST).exists():
            manifest = verify_install_bundle(project, root)
            break
    else:
        return
    if manifest['format_version'] != 2:
        return
    from .process import check_cancelled
    from .system_python import SystemPythonError, validate_python
    from .system_node import SystemNodeError, validate_node, find_npm_cli
    check_cancelled()
    hosts = manifest['host_runtimes']
    if 'python' in hosts:
        if python_executable is None:
            raise BundleHostRuntimeError('python')
        try:
            validate_python(python_executable)
        except SystemPythonError:
            raise BundleHostRuntimeError('python') from None
    if not any(name in hosts for name in ('node', 'npm')):
        return
    required = 'node' if 'node' in hosts else 'npm'
    if node_executable is None:
        raise BundleHostRuntimeError(required)
    try:
        node = validate_node(node_executable)
    except SystemNodeError:
        raise BundleHostRuntimeError(required) from None
    if 'npm' in hosts and find_npm_cli(node, '10.9.4', compatible=True) is None:
        raise BundleHostRuntimeError('npm')
