"""Manager-only port selection and journaled changes to stopped profiles.

Callers hold exclusive lifecycle leases. CLI provisioning keeps its existing
fixed-port semantics; missing provenance in an old profile means manual.
"""
from contextlib import ExitStack
import errno
import json
import socket

from . import installation_profiles as profiles
from .installation_permissions import require_unlinked
from .model import LauncherError
from .process import check_cancelled

PORT_FIELDS = ('backend_port', 'frontend_port')
CONNECTION_FIELDS = frozenset({'host', *PORT_FIELDS, 'tls_cert_file', 'tls_key_file', 'port_modes'})


class ConnectionError(LauncherError):
    def __init__(self, field, *, occupied=False):
        self.field = field
        self.code = 'port_unavailable' if occupied else 'connection_override_invalid'
        super().__init__('Seçilen port kullanılıyor; ilgili portu değiştirin veya otomatik seçimi kullanın.'
                         if occupied else 'Bağlantı ayarları özel yapılandırmayla çelişiyor; ilgili alanı kontrol edin.')


def select_ports(profile, overrides, *, automatic=()):
    """Reserve both candidates during selection; actual server bind is authoritative."""
    if profile and profile.get('name') != 'dev':
        raise ConnectionError('profile')
    old = profile or {}
    modes, selected = {}, {}
    with ExitStack() as stack:
        for field, default in zip(PORT_FIELDS, (8000, 5173)):
            check_cancelled()
            explicit = overrides.get(field) is not None
            mode = ('automatic' if field in automatic else 'manual' if explicit else
                    old.get('port_modes', {}).get(field, 'manual') if profile else 'automatic')
            port = overrides[field] if explicit else old.get(field, default)
            if type(port) is not int or not 1 <= port <= 65535:
                raise ConnectionError(field)
            probe = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError as error:
                if error.errno != errno.EADDRINUSE and getattr(error, 'winerror', None) != 10048:
                    raise ConnectionError(field) from None
                if mode != 'automatic':
                    raise ConnectionError(field, occupied=True) from None
                probe.bind(('127.0.0.1', 0))
            selected[field] = probe.getsockname()[1]
            modes[field] = mode
    return {**selected, 'port_modes': modes}


def connection_environment(previous, updated, values):
    """Only replace generated bind values, never custom origins or credentials."""
    before, after = profiles._configuration(previous), profiles._configuration(updated)
    result = dict(values)
    for key, value in after.items():
        if value == before.get(key):
            continue
        if key in result and result[key] != before.get(key):
            error = ConnectionError('env_file')
            error.setting = key  # Fixed configuration key; never a value.
            raise error
        result[key] = value
    return result


def update_connection(project, profile, changes):
    """Atomically publish profile/environment with an owned resumable journal."""
    if set(changes) - CONNECTION_FIELDS:
        raise ConnectionError('profile')
    home, path, env = profiles._paths(project, profile['name'], profile['installation_home'])
    pending = path.with_name(profile['name'] + '.pending.json')
    require_unlinked(pending)
    profiles._recover_pending(project, profile['name'], home, path, env, pending)
    replacements = {key: value for key, value in changes.items() if key in profiles.TLS_PATH_FIELDS}
    current = profiles.load_profile(project, profile['name'], home, tls_replacements=replacements)
    if current != profile:
        raise ConnectionError('profile')
    updated = {**current, **changes}
    if updated == current:
        return current
    profiles._validate_options(updated)
    values = connection_environment(current, updated, profiles.read_environment(env))
    profiles._validate_environment(updated, values)
    profiles._require_separate(home, profile['name'], values, current['source_root'])
    profiles._check_inherited(values, str(env))
    metadata = profiles._pending_metadata(updated, values, operation='connection',
        previous_environment=env.read_bytes(), previous_profile=path.read_bytes())
    profiles._write_new(pending, metadata)
    profiles._write_replace(env, profiles._environment_content(values))
    profiles._write_replace(path, json.dumps(updated, indent=2) + '\n')
    pending.unlink()
    return profiles.load_profile(project, profile['name'], home)
