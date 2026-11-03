"""Lightweight desktop launch paths, independent of installation modules."""
from pathlib import Path
import os
import sys


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
              'tls_cert_file', 'tls_key_file', 'output'}
    repository = result.get('repository')
    if repository and '://' not in str(repository):
        fields.add('repository')
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
