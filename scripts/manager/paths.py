"""Lightweight desktop launch paths, independent of installation modules."""
from pathlib import Path
import os
import sys
import json


def startup_values(saved: dict, explicit_root: Path | None) -> dict:
    """Read only bounded media metadata here; the worker verifies every byte."""
    values = dict(saved)
    if getattr(sys, 'frozen', False):
        directory = Path(sys.executable).resolve().parent
        manifest = directory / 'manager-manifest.json'
        try:
            if manifest.stat().st_size <= 8 * 1024 * 1024:
                metadata = json.loads(manifest.read_text(encoding='utf-8'))
                if metadata.get('format_version') == 2 and metadata.get('complete') is True:
                    for field in ('python_command', 'node_command', 'assets', 'feature_catalog', 'ca_file',
                                  'output', 'env_file', 'tls_cert_file', 'tls_key_file', 'manager_distribution'):
                        values[field] = ''
                    values.update(source_root=str(directory / 'source'), offline_dir=str(directory),
                                  source_mode='offline', repository='', python_index_url='', npm_registry_url='')
        except (OSError, ValueError, AttributeError):
            pass  # No claim of verified readiness until worker inspection.
    if explicit_root is not None:
        values['source_root'] = str(explicit_root)
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
