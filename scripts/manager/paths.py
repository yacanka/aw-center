"""Lightweight desktop launch paths, independent of installation modules."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import sys
import json
import uuid
import hashlib

from scripts.launcher.model import LauncherError


_PROFILE_CONNECTION_FIELDS = ('host', 'backend_port')
_GLOBAL_CONNECTION_FIELDS = {
    'host', 'backend_port', 'frontend_port',
    'dev_host', 'dev_backend_port', 'prod_host', 'prod_backend_port',
}


def new_bundle_output(parent: Path | None = None) -> Path:
    """Choose a new destination without filesystem I/O on the Tk thread."""
    if parent is None:
        from scripts.launcher.installation_profiles import installation_home
        parent = installation_home() / 'exports'
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime('%d.%m.%Y-%H%M%S')
    return Path(parent) / f'AWCenter-offline-{stamp}-{uuid.uuid4().hex[:12]}'


def startup_values(saved: dict, explicit_root: Path | None) -> dict:
    """Read only bounded media metadata here; the worker verifies every byte."""
    values = dict(saved)
    # Older versions stored one active form. Attribute its inputs to the last
    # selected profile before a different package restores its own selection.
    last_profile = saved.get('profile', 'dev')
    for field in _PROFILE_CONNECTION_FIELDS:
        if field in saved:
            values[f'{last_profile}_{field}'] = saved[field]
    values.setdefault('source_selection', 'explicit' if saved.get('source_root') else 'automatic')
    if getattr(sys, 'frozen', False):
        directory = Path(sys.executable).resolve().parent
        manifest = directory / 'manager-manifest.json'
        try:
            if manifest.stat().st_size <= 8 * 1024 * 1024:
                metadata = json.loads(manifest.read_text(encoding='utf-8'))
                if metadata.get('format_version') == 2 and (metadata.get('complete') is True or metadata.get('host_runtimes')):
                    identity = [str(directory), str(metadata.get('source_fingerprint', ''))]
                    if metadata.get('offline_start'):
                        identity.append(json.dumps(metadata.get('host_runtimes', {}), sort_keys=True))
                    context = hashlib.sha256('\0'.join(identity).encode()).hexdigest()
                    history = dict(saved.get('_contexts', {}))
                    previous = saved.get('_media_context')
                    if previous and previous != context:
                        history[previous] = {key: value for key, value in saved.items() if not key.startswith('_')}
                    if previous != context:
                        for field in ('dev_env_file', 'prod_env_file'):
                            values.pop(field, None)
                        if context in history:
                            # Connection inputs follow the profile across media, including an explicit clear.
                            values.update({key: value for key, value in history[context].items()
                                           if key not in _GLOBAL_CONNECTION_FIELDS})
                        else:
                            if saved and not previous:
                                legacy = hashlib.sha256(('legacy:' + str(saved.get('source_root', ''))).encode()).hexdigest()
                                history[legacy] = {key: value for key, value in saved.items() if not key.startswith('_')}
                            for field in ('python_command', 'node_command', 'assets', 'feature_catalog', 'ca_file',
                                          'output', 'env_file', 'tls_cert_file', 'tls_key_file', 'manager_distribution'):
                                values[field] = ''
                            values.update(bundle_import='', bundle_host_node=False, bundle_host_python=False,
                                          install_python=False, install_node=False)
                            # New media must never broaden an explicit restrictive policy.
                            mode = 'offline' if metadata.get('offline_start') else ('corporate' if saved.get('source_mode') == 'corporate' else 'offline')
                            repository = saved.get('repository', '')
                            values.update(source_root=str(directory / 'source'), source_selection='automatic',
                                          offline_dir=str(directory), source_mode=mode,
                                          repository=repository if mode == 'corporate' and repository.startswith('https://') else '')
                            if mode != 'corporate':
                                values.update(python_index_url='', npm_registry_url='')
                    if previous != context:
                        values['validation_policy'] = history.get(context, {}).get('validation_policy', 'developer')
                    values.update(_media_context=context, _contexts=history)
        except (OSError, ValueError, AttributeError):
            pass  # No claim of verified readiness until worker inspection.
    if explicit_root is not None:
        if not values.get('source_root') or explicit_root != Path(values['source_root']):
            values['validation_policy'] = 'developer'
        values['source_root'] = str(explicit_root)
        values['source_selection'] = 'explicit'
    if values.get('validation_policy', 'developer') not in ('managed', 'developer'):
        values['validation_policy'] = 'developer'
    selected_profile = values.get('profile', 'dev')
    for field in _PROFILE_CONNECTION_FIELDS:
        if field in values:
            values[field] = values.get(f'{selected_profile}_{field}', '')
    return values


class OfflinePackageError(LauncherError):
    field = 'offline_dir'
    remedy = 'ZIP dosyasının tamamını çıkarın ve dependencies/manifest.json içeren paket kökünü veya manifest.json içeren bağımlılık klasörünü seçin.'

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def offline_package_root(selected: Path) -> Path:
    """Recognize only documented layouts, without walking or hashing the package."""
    from scripts.launcher.installation_permissions import require_unlinked

    require_unlinked(selected)
    missing = OfflinePackageError('offline_manifest_missing', 'Seçilen klasörde çevrimdışı bağımlılık manifesti bulunamadı.')
    if not selected.is_dir():
        raise missing

    root = selected
    if selected.name.casefold() in {'wheels', 'npm-cache'} and (selected.parent / 'manifest.json').is_file():
        root = selected.parent
    if root.name.casefold() in {'source', 'dependencies', 'runtimes'}:
        parent = root.parent
        if any((parent / marker).is_file() for marker in ('install-manifest.json', 'manager-manifest.json')):
            root = parent

    manifest = root / 'dependencies/manifest.json'
    if not manifest.is_file() and not (root / 'install-manifest.json').is_file():
        manifest = root / 'manifest.json'
    require_unlinked(manifest)
    if not manifest.is_file():
        raise missing
    if (root / 'install-manifest.json').is_file():
        for component in ('wheels', 'npm-cache'):
            if not (manifest.parent / component).is_dir():
                raise OfflinePackageError('offline_component_missing',
                                          f'Çevrimdışı pakette dependencies/{component} klasörü eksik.')
    return root


def default_source_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'source'
    return Path(__file__).resolve().parents[2]


def worker_directory() -> Path:
    """The explicit child cwd, shared by path admission and actual spawning."""
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).absolute().parents[2]


def normalize_task_paths(values: dict) -> dict:
    """Resolve form paths lexically once, without touching UNC/disks on Tk.

    The immutable request and its conflict claims must use identical paths.
    Expand only the current user's ~ from environment, never an account lookup.
    Reparse/symlink checks remain in the owning worker before any mutation.
    """
    result = dict(values)
    fields = {'source_root', 'offline_dir', 'bundle_import', 'ca_file', 'assets', 'feature_catalog',
              'tls_cert_file', 'tls_key_file', 'output', 'env_file', 'manager_distribution'}
    repository = result.get('repository')
    if repository and '://' not in str(repository):
        fields.add('repository')
    for field in ('python_command', 'node_command'):
        selection = result.get(field, '')
        if len(selection) >= 2 and selection[0] == selection[-1] and selection[0] in {'"', "'"}:
            selection = selection[1:-1]
            result[field] = selection
        if '/' in selection or '\\' in selection:
            fields.add(field)
    base = str(worker_directory())
    for field in fields:
        value = result.get(field)
        if not value:
            continue
        value = str(value)
        if value == '~' or value.startswith(('~/', '~\\')):
            home = os.environ.get('USERPROFILE' if os.name == 'nt' else 'HOME')
            if home:
                value = os.path.join(home, value[2:]) if len(value) > 1 else home
        result[field] = os.path.abspath(os.path.normpath(os.path.join(base, value)))
    return result
