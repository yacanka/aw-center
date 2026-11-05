"""Lightweight desktop launch paths, independent of installation modules."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import sys
import json
import uuid
import hashlib


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
    values.setdefault('source_selection', 'explicit' if saved.get('source_root') else 'automatic')
    if getattr(sys, 'frozen', False):
        directory = Path(sys.executable).resolve().parent
        manifest = directory / 'manager-manifest.json'
        try:
            if manifest.stat().st_size <= 8 * 1024 * 1024:
                metadata = json.loads(manifest.read_text(encoding='utf-8'))
                if metadata.get('format_version') == 2 and metadata.get('complete') is True:
                    context = hashlib.sha256((str(directory) + '\0' + str(metadata.get('source_fingerprint', ''))).encode()).hexdigest()
                    history = dict(saved.get('_contexts', {}))
                    previous = saved.get('_media_context')
                    if previous and previous != context:
                        history[previous] = {key: value for key, value in saved.items() if not key.startswith('_')}
                    if previous != context:
                        if context in history:
                            values.update(history[context])
                        else:
                            if saved and not previous:
                                legacy = hashlib.sha256(('legacy:' + str(saved.get('source_root', ''))).encode()).hexdigest()
                                history[legacy] = {key: value for key, value in saved.items() if not key.startswith('_')}
                            for field in ('python_command', 'node_command', 'assets', 'feature_catalog', 'ca_file',
                                          'output', 'env_file', 'tls_cert_file', 'tls_key_file', 'manager_distribution',
                                          'host', 'backend_port', 'frontend_port'):
                                values[field] = ''
                            # New media must never broaden an explicit restrictive policy.
                            mode = 'corporate' if saved.get('source_mode') == 'corporate' else 'offline'
                            repository = saved.get('repository', '')
                            values.update(source_root=str(directory / 'source'), source_selection='automatic',
                                          offline_dir=str(directory), source_mode=mode,
                                          repository=repository if mode == 'corporate' and repository.startswith('https://') else '')
                            if mode != 'corporate':
                                values.update(python_index_url='', npm_registry_url='')
                    values.update(_media_context=context, _contexts=history)
        except (OSError, ValueError, AttributeError):
            pass  # No claim of verified readiness until worker inspection.
    if explicit_root is not None:
        values['source_root'] = str(explicit_root)
        values['source_selection'] = 'explicit'
    return values


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
    fields = {'source_root', 'offline_dir', 'ca_file', 'assets', 'feature_catalog',
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
