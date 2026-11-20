"""Fresh Manager inputs for local SQLite; runtime copies are outputs, not layers.

The resolver only reads configuration. Publishing requires the caller's existing
exclusive lifecycle leases and uses the installation pending journal. Secrets
are retained separately by normalized database identity, never in UI preferences.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets

from . import installation_profiles as profiles
from .installation_connection import PORT_FIELDS, select_ports
from .installation_env import read_selected_environment
from .installation_permissions import require_private, require_unlinked
from .model import LauncherError


IDENTITY_KEYS = ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY')
ASSET_PATH_KEYS = frozenset({
    'MODEL_RUNTIME_DIR', 'CUSTOM_TEMPLATE_DIR', 'WORD_TRANSLATION_TR_EN_MODEL',
    'WORD_TRANSLATION_EN_TR_MODEL', 'WORD_ANALYZER_BI_MODEL',
    'WORD_ANALYZER_CROSS_MODEL', 'COVER_PAGE_TEMPLATE_PATH',
})
DIRECTORY_KEYS = frozenset({'PRIVATE_MEDIA_ROOT', 'CACHE_DIRECTORY', 'MODEL_RUNTIME_DIR',
                            'CUSTOM_TEMPLATE_DIR', 'STATIC_ROOT', 'MEDIA_ROOT',
                            'WORD_TRANSLATION_TR_EN_MODEL', 'WORD_TRANSLATION_EN_TR_MODEL',
                            'WORD_ANALYZER_BI_MODEL', 'WORD_ANALYZER_CROSS_MODEL'})
PATH_KEYS = DIRECTORY_KEYS | ASSET_PATH_KEYS


def _invalid(*keys):
    return profiles.EnvironmentImportError('env_local_setting_invalid', keys=keys)


def _require_stable_path(project, path, key=None):
    normalized = Path(os.path.normcase(os.path.abspath(path)))
    roots = (project.venv, project.frontend / 'node_modules', project.frontend / 'dist',
             *(project.root / '.runtime' / name for name in
               ('npm-backups', 'venv-backups', 'frontend-build-backups', 'frontend-build')))
    if any(normalized.is_relative_to(Path(os.path.normcase(os.path.abspath(root)))) for root in roots):
        raise profiles.EnvironmentImportError('env_local_path_unsafe', keys=(key,) if key else ())


def _selected_environment_path(project, args):
    if args.profile != 'dev':
        raise LauncherError('Local configuration is available only for development')
    source = getattr(args, 'env_file', None)
    if not source:
        return None
    home, _path, _env = profiles._paths(project, 'dev', None)
    source = Path(os.path.normcase(os.path.abspath(source)))
    _require_stable_path(project, source)
    config = Path(os.path.normcase(str(home / 'config')))
    generated = {config / (name + suffix) for name in ('dev', 'prod')
                 for suffix in ('.env', '.profile.json', '.pending.json')}
    if source in generated or source.is_relative_to(config / 'local-keys'):
        raise profiles.EnvironmentImportError('env_runtime_source_invalid')
    require_unlinked(source)
    return source


def _selected_environment(project, args):
    source = _selected_environment_path(project, args)
    return read_selected_environment(project, 'dev', source) if source is not None else {}


def _host(value):
    if not isinstance(value, str):
        raise _invalid('IPV4_ADDRESS')
    if isinstance(value, str) and value.casefold() == 'localhost':
        return 'localhost'
    try:
        address = ipaddress.ip_address(value)
        if address.version != 4 or address.is_multicast or address.is_reserved:
            raise ValueError
    except ValueError:
        raise _invalid('IPV4_ADDRESS') from None
    return value


def validate_marker(profile):
    """Admit only versioned, non-secret provenance on local development profiles."""
    marker = profile.get('local_configuration')
    if (profile.get('name') != 'dev' or not isinstance(marker, dict)
            or set(marker) - {'version', 'database_identity', 'asset_path_keys', 'overrides', 'state_paths'}
            or not {'version', 'database_identity', 'asset_path_keys', 'overrides'}.issubset(marker)
            or type(marker['version']) is not int or marker['version'] != 1
            or not isinstance(marker['database_identity'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', marker['database_identity'])
            or not isinstance(marker['asset_path_keys'], list)
            or any(not isinstance(key, str) or key not in ASSET_PATH_KEYS for key in marker['asset_path_keys'])
            or len(set(marker['asset_path_keys'])) != len(marker['asset_path_keys'])
            or not isinstance(marker['overrides'], dict)
            or set(marker['overrides']) - {'host', *PORT_FIELDS}):
        raise LauncherError('Invalid local configuration metadata')
    for field, value in marker['overrides'].items():
        if field == 'host':
            if not isinstance(value, str):
                raise LauncherError('Invalid local configuration metadata')
            _host(value)
        elif value != 'auto' and (type(value) is not int or not 1 <= value <= 65535):
            raise LauncherError('Invalid local configuration metadata')
    if 'state_paths' in marker:
        _validate_state_paths(marker['state_paths'])


def _validate_state_paths(paths):
    from .installation_bundle import _relative_path
    if (not isinstance(paths, dict) or set(paths) != {'files', 'directories'}
            or any(not isinstance(paths[key], list) for key in paths)
            or sum(len(entries) for entries in paths.values()) > 256):
        raise LauncherError('Invalid local state path metadata')
    for entries in paths.values():
        folded = set()
        for value in entries:
            if (not isinstance(value, str) or len(value) > 1024 or value == '.'
                    or any(ord(character) == 127 for character in value)):
                raise LauncherError('Invalid local state path metadata')
            _relative_path(value)
            if value.casefold() in folded:
                raise LauncherError('Invalid local state path metadata')
            folded.add(value.casefold())
    if len(json.dumps(paths).encode('utf-8')) > 64 * 1024:
        raise LauncherError('Local state path history is too large; existing state was preserved')


def _snapshot_state_paths(project, values, history):
    def remember(path, kind):
        try:
            relative = path.relative_to(project.root).as_posix()
        except ValueError:
            return  # External data never becomes an exemption inside the source.
        history[kind].add(relative)
    database = database_path(project, values)
    for suffix in ('', '-wal', '-shm', '-journal'):
        remember(Path(str(database) + suffix), 'files')
    for key in PATH_KEYS:
        if values.get(key):
            path = _absolute_path(project, values[key], key)
            remember(path, 'directories' if key in DIRECTORY_KEYS else 'files')


def _manifest_owned_input(project, relative):
    from .installation_bundle import _json_object
    manifest = project.root / 'manager-source-manifest.json'
    require_unlinked(manifest)
    if not manifest.exists():
        return False
    # Classification is not verification. The Manager must still validate every
    # manifest artifact; only this read-only source input needs no exemption.
    artifacts = _json_object(manifest).get('artifacts', ())
    return isinstance(artifacts, list) and any(
        isinstance(entry, dict) and isinstance(entry.get('path'), str)
        and entry['path'].casefold() == relative.casefold() for entry in artifacts)


def _state_paths(project, args, previous, values):
    history = {'files': set(), 'directories': set()}
    if previous:
        if previous.get('source_root') != str(project.root.resolve()):
            raise LauncherError('Local state history belongs to a different source checkout')
        marker = previous.get('local_configuration', {})
        if marker:
            validate_marker(previous)
        for kind, entries in marker.get('state_paths', {}).items():
            history[kind].update(entries)
        _snapshot_state_paths(project, profiles.read_profile_environment(previous), history)
    _snapshot_state_paths(project, values, history)
    selected = getattr(args, 'env_file', None)
    if selected:
        source = Path(os.path.abspath(selected))
        name = source.name.casefold()
        executable = {'.py', '.pyw', '.pth', '.exe', '.dll', '.com', '.cmd', '.bat',
                      '.ps1', '.vbs', '.js', '.mjs', '.cjs', '.sh'}
        config_name = name == '.env' or name.startswith('.env.') or name.endswith('.env')
        if (config_name and source.suffix.casefold() not in executable and source.is_relative_to(project.root)):
            relative = source.relative_to(project.root).as_posix()
            if not _manifest_owned_input(project, relative):
                history['files'].add(relative)
    result = {kind: sorted({value.casefold(): value for value in sorted(entries)}.values())
              for kind, entries in history.items()}
    _validate_state_paths(result)
    return result


def _absolute_path(project, value, key):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '\0\r\n'):
        raise _invalid(key)
    path = Path(value)
    if not path.is_absolute():
        path = project.backend / path
    path = Path(os.path.abspath(path))
    require_unlinked(path)
    _require_stable_path(project, path, key)
    return path


def database_path(project, values):
    """Use Django's backend cwd for relative SQLite filenames, never dotenv cwd."""
    value = values.get('DATABASE_URL', '')
    if (not isinstance(value, str) or not value.startswith('sqlite:///')
            or value == 'sqlite:///:memory:' or '?' in value or '#' in value or '%' in value):
        raise _invalid('DATABASE_URL')
    path = _absolute_path(project, value[len('sqlite:///'):], 'DATABASE_URL')
    from .installation_state import require_local_ntfs
    require_local_ntfs(path)
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise _invalid('DATABASE_URL')
    return path


def _database_identity(database):
    value = os.path.normcase(str(database))
    return hashlib.sha256(('dev\0' + value).encode('utf-8')).hexdigest()


def _identity_file(home, identity):
    return Path(home) / 'config' / 'local-keys' / (identity + '.env')


def _read_keys(home, identity):
    path = _identity_file(home, identity)
    require_unlinked(path)
    if not path.exists():
        return {}
    require_private(path.parent)
    require_private(path)
    if path.stat().st_size > 16 * 1024:
        raise LauncherError('Local database key record is invalid; values have been withheld')
    values = profiles.read_environment(path)
    if set(values) != set(IDENTITY_KEYS):
        raise LauncherError('Local database key record is invalid; values have been withheld')
    return values


def _keys(project, profile, values, database, home):
    identity = _database_identity(database)
    known = _read_keys(home, identity)
    if profile:
        previous = profiles.read_profile_environment(profile)
        if database_path(project, previous) == database:
            known = {**known, **{key: previous[key] for key in IDENTITY_KEYS}}
    missing = [key for key in IDENTITY_KEYS if not values.get(key, '').strip()]
    if any(key not in known for key in missing) and database.exists() and database.stat().st_size:
        raise profiles.EnvironmentImportError('env_local_identity_required', keys=missing)
    for key in missing:
        if key in known:
            values[key] = known[key]
        elif key == 'SECRET_KEY':
            values[key] = secrets.token_urlsafe(64)
        else:
            values[key] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii')
    return identity


def _raw_overrides(args):
    result = {}
    if getattr(args, 'host', None):
        result['host'] = args.host
    for field in PORT_FIELDS:
        if field in getattr(args, 'automatic_ports', ()):
            result[field] = 'auto'
        elif getattr(args, field, None) is not None:
            result[field] = getattr(args, field)
    return result


def _port(value, key):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise _invalid(key)
    port = int(value)
    if not 1 <= port <= 65535:
        raise _invalid(key)
    return port


def _connection(profile, args, selected, previous):
    overrides = _raw_overrides(args)
    profile['host'] = _host(overrides.get('host') or selected.get('IPV4_ADDRESS', '127.0.0.1'))
    modes = {}
    before = (previous or {}).get('local_configuration', {}).get('overrides', {})
    for field, key, default in (('backend_port', 'DEV_BACKEND_PORT', 8000),
                                ('frontend_port', 'DEV_FRONTEND_PORT', 5173)):
        source = selected.get(key, selected.get('PORT') if field == 'backend_port' else None)
        override = overrides.get(field)
        automatic = override == 'auto' or override is None and source is None
        value = default if automatic else override if override is not None else source
        if (automatic and previous and previous.get('host') == profile['host']
                and previous.get('port_modes', {}).get(field) == 'automatic'
                and before.get(field) == override):
            value = previous[field]  # An allocation hint; never a settings layer.
        profile[field] = _port(value, key)
        modes[field] = 'automatic' if automatic else 'manual'
    profile['port_modes'] = modes
    return overrides


def _bind_values(profile, values, selected):
    values.update(IPV4_ADDRESS=profile['host'], PORT=str(profile['backend_port']),
                  DEV_BACKEND_PORT=str(profile['backend_port']), DEV_FRONTEND_PORT=str(profile['frontend_port']))
    hosts = ['127.0.0.1', 'localhost']
    if profile['host'] != '0.0.0.0' and profile['host'] not in hosts:
        hosts.append(profile['host'])
    origins = [f'http://{host}:{profile[field]}' for field in ('frontend_port', 'backend_port') for host in hosts]
    for key in ('CSRF_TRUSTED_ORIGINS', 'DEV_SERVER_ORIGINS'):
        extras = [item.strip() for item in selected.get(key, '').split(',') if item.strip()]
        values[key] = ','.join(dict.fromkeys([*extras, *origins]))
    allowed = [item.strip() for item in selected.get('ALLOWED_HOSTS', '').split(',') if item.strip()]
    values['ALLOWED_HOSTS'] = ','.join(dict.fromkeys([*allowed, *hosts]))
    browser_host = '127.0.0.1' if profile['host'] == '0.0.0.0' else profile['host']
    origin = f"http://{browser_host}:{profile['frontend_port']}"
    for key, suffix in (('FRONTEND_RESET_URL', '/app/login'), ('FRONTEND_INVITATION_URL', '/app/invite')):
        values[key] = selected.get(key, origin + suffix)


def validate_local_environment(profile, values):
    """Validate actual local storage/bind constraints instead of generated equality."""
    from .model import Project
    validate_marker(profile)
    root = Path(profile['source_root'])
    project = Project(root, root / 'backend/manage.py', root / 'frontend/package.json', None)
    database = database_path(project, values)
    if _database_identity(database) != profile['local_configuration']['database_identity']:
        raise _invalid('DATABASE_URL')
    if values.get('AWCENTER_DEPLOYMENT_MODE') != 'development':
        raise _invalid('AWCENTER_DEPLOYMENT_MODE')
    expected = {'IPV4_ADDRESS': profile['host'], 'PORT': str(profile['backend_port']),
                'DEV_BACKEND_PORT': str(profile['backend_port']), 'DEV_FRONTEND_PORT': str(profile['frontend_port'])}
    conflicts = [key for key, value in expected.items() if values.get(key) != value]
    if conflicts:
        raise _invalid(*conflicts)
    for key in PATH_KEYS:
        value = values.get(key, '')
        if not value:
            if key == 'PRIVATE_MEDIA_ROOT':
                raise _invalid(key)
            continue
        path = _absolute_path(project, value, key)
        if not Path(value).is_absolute() or str(path) != str(Path(value)):
            raise _invalid(key)
        if path.exists() and (path.is_dir() != (key in DIRECTORY_KEYS)):
            raise _invalid(key)
    media = Path(values['PRIVATE_MEDIA_ROOT'])
    home = Path(profile['installation_home'])
    if (media == database or database.is_relative_to(media) or media == root or root.is_relative_to(media)
            or home.is_relative_to(media) or media.is_relative_to(home / 'config')
            or media.is_relative_to(home / 'backups') or (home / 'backups').is_relative_to(media)
            or database.is_relative_to(home / 'config') or database.is_relative_to(home / 'backups')):
        raise _invalid('DATABASE_URL', 'PRIVATE_MEDIA_ROOT')


def resolve_local_configuration(project, args, profile=None):
    """Return candidate metadata/values from fresh defaults, source and raw inputs.

    This performs no writes, runtime setup, socket bind or database open. Previous
    runtime values are consulted only for the same database's identity keys and
    an unchanged automatic port allocation hint.
    """
    selected = _selected_environment(project, args)
    return _resolve_configuration(project, args, profile, selected)


def _resolve_configuration(project, args, profile, selected):
    if args.profile != 'dev':
        raise LauncherError('Local configuration is available only for development')
    home, _path, env = profiles._paths(project, 'dev', None)
    candidate = dict(profile or {
        'version': profiles.PROFILE_VERSION, 'name': 'dev', 'source_root': str(project.root.resolve()),
        'installation_home': str(home), 'env_file': str(env), 'host': '127.0.0.1',
        'backend_port': 8000, 'frontend_port': 5173, 'tls_cert_file': None, 'tls_key_file': None,
        'asset_set': 'default', 'exclude_doors': False,
    })
    if getattr(args, 'asset_set', None):
        candidate['asset_set'] = args.asset_set
    overrides = _connection(candidate, args, selected, profile)
    values = {**profiles._configuration(candidate), **selected}
    for key in PATH_KEYS:
        if values.get(key):
            values[key] = _absolute_path(project, values[key], key).as_posix()
    database = database_path(project, values)
    values['DATABASE_URL'] = 'sqlite:///' + database.as_posix()
    identity = _keys(project, profile, values, database, home)
    candidate['local_configuration'] = {'version': 1, 'database_identity': identity,
        'asset_path_keys': sorted(ASSET_PATH_KEYS.intersection(selected)), 'overrides': overrides}
    values = profiles._asset_values(candidate, values)
    _bind_values(candidate, values, selected)
    candidate['local_configuration']['state_paths'] = _state_paths(project, args, profile, values)
    profiles._validate_options(candidate)
    profiles._validate_environment(candidate, values)
    profiles._require_separate(home, 'dev', values, candidate['source_root'])
    profiles._check_inherited(values, str(env))
    return candidate, values


def configuration_changed(project, args, profile):
    candidate, values = resolve_local_configuration(project, args, profile)
    current = profiles.read_profile_environment(profile)
    if 'local_configuration' not in profile:
        # A canonical legacy snapshot needs no marker-only rewrite. Any actual
        # settings change adopts the local contract under preparation leases.
        candidate.pop('local_configuration')
        if 'port_modes' not in profile:
            candidate.pop('port_modes')
        for key in ASSET_PATH_KEYS - {'MODEL_RUNTIME_DIR', 'CUSTOM_TEMPLATE_DIR'}:
            if key not in current:
                values.pop(key, None)
    return candidate != profile or values != current


def _save_keys(profile, values, *, identity=None):
    identity = identity or profile['local_configuration']['database_identity']
    path = _identity_file(profile['installation_home'], identity)
    profiles._create_private_directory(path.parent, root=Path(profile['installation_home']))
    content = profiles._environment_content({key: values[key] for key in IDENTITY_KEYS})
    if path.exists():
        require_private(path)
        if path.read_text(encoding='utf-8') != content:
            profiles._write_replace(path, content)
    else:
        profiles._write_new(path, content)


def _preserve_profile_keys(project, profile):
    # Legacy profiles have no per-database record. Save their verified keys before
    # publishing another database's runtime copy, including on journal recovery.
    values = profiles.read_profile_environment(profile)
    profiles._validate_environment(profile, values)
    identity = _database_identity(database_path(project, values))
    _save_keys(profile, values, identity=identity)


def _prepare_database_parent(project, values):
    parent = database_path(project, values).parent
    require_unlinked(parent)
    if parent.exists():
        if not parent.is_dir():
            raise _invalid('DATABASE_URL')
        return
    first_missing = parent
    while not first_missing.parent.exists():
        first_missing = first_missing.parent
    # Existing source/user directories retain their ownership and permissions.
    # Only this newly selected, missing directory subtree becomes owner-only.
    profiles._create_private_directory(parent, root=first_missing)


def apply_local_configuration(project, args, profile=None):
    """Resolve and publish under exclusive lifecycle leases, preserving source bytes."""
    _selected_environment_path(project, args)
    home, path, env = profiles._paths(project, 'dev', None)
    pending = path.with_name('dev.pending.json')
    require_unlinked(pending)
    profiles._recover_pending(project, 'dev', home, path, env, pending)
    source = _selected_environment(project, args)
    current = profiles.load_profile(project, 'dev', home) if path.exists() else None
    if profile is not None and current != profile:
        raise LauncherError('Installation profile changed; reload before applying local settings')
    if current is None:
        profiles.require_new_environment(env)
    candidate, values = _resolve_configuration(project, args, current, source)
    automatic = tuple(field for field in PORT_FIELDS if candidate['port_modes'][field] == 'automatic')
    selected = select_ports(candidate, {field: candidate[field] for field in PORT_FIELDS}, automatic=automatic,
                            host=candidate['host'])
    if any(candidate[field] != selected[field] for field in PORT_FIELDS):
        candidate.update(selected)
        _bind_values(candidate, values, source)
    if current is None and getattr(args, 'manager_ensure', False) and getattr(args, 'validation_policy', None) == 'developer':
        # Once a profile exists, absent runtime pointers mean managed tools.
        # Record first-use choices with the profile so retries keep its system tools.
        from .runtime_selection import tool_choices
        candidate.update({field: str(path) for field, path in tool_choices(args).items()})
        profiles._validate_options(candidate)
    profiles._validate_environment(candidate, values)
    profiles._require_separate(home, 'dev', values, candidate['source_root'])
    profiles._check_inherited(values, str(env))
    _prepare_database_parent(project, values)
    if current == candidate and profiles.read_profile_environment(current) == values:
        _save_keys(candidate, values)
        return current
    profiles._create_private_directory(home, root=home)
    profiles._create_private_directory(path.parent, root=home)
    if current:
        _preserve_profile_keys(project, current)
    document = json.loads(profiles._pending_metadata(candidate, values, operation='local',
        previous_environment=env.read_bytes() if current else None,
        previous_profile=path.read_bytes() if current else None))
    document['environment'] = values
    profiles._write_new(pending, json.dumps(document, indent=2) + '\n')
    if current:
        profiles._write_replace(env, profiles._environment_content(values))
        profiles._write_replace(path, json.dumps(candidate, indent=2) + '\n')
    else:
        profiles._write_new(env, profiles._environment_content(values))
        profiles._write_new(path, json.dumps(candidate, indent=2) + '\n')
    _save_keys(candidate, values)
    pending.unlink()
    return profiles.load_profile(project, 'dev', home)


def recover_local_configuration(project, candidate, document, path, env, pending):
    """Complete only the exact private candidate recorded before publication."""
    if 'local_configuration' not in candidate:
        raise ValueError
    values = document.get('environment')
    if (not isinstance(values, dict)
            or any(not isinstance(key, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key)
                   or not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value)
                   for key, value in values.items())
            or profiles._digest(profiles._environment_content(values)) != document['environment_sha256']):
        raise ValueError
    previous_env = document.get('previous_environment_sha256')
    previous_profile = document.get('previous_profile_sha256')
    if bool(previous_env) != bool(previous_profile):
        raise ValueError
    if env.exists():
        require_private(env)
        digest = profiles._digest(env.read_bytes())
        if digest not in {document['environment_sha256'], previous_env}:
            raise ValueError
    elif previous_env:
        raise ValueError
    if path.exists():
        require_private(path)
        content = path.read_bytes()
        if json.loads(content) != candidate and profiles._digest(content) != previous_profile:
            raise ValueError
    elif previous_profile:
        raise ValueError
    profiles._validate_environment(candidate, values)
    home = Path(candidate['installation_home'])
    profiles._require_separate(home, 'dev', values, candidate['source_root'])
    profiles._check_inherited(values, str(env))
    _prepare_database_parent(project, values)
    if (previous_env and profiles._digest(env.read_bytes()) == previous_env
            and profiles._digest(path.read_bytes()) == previous_profile):
        _preserve_profile_keys(project, profiles.load_profile(project, 'dev', home))
    if not env.exists():
        profiles._write_new(env, profiles._environment_content(values))
    elif profiles._digest(env.read_bytes()) != document['environment_sha256']:
        profiles._write_replace(env, profiles._environment_content(values))
    if not path.exists():
        profiles._write_new(path, json.dumps(candidate, indent=2) + '\n')
    elif json.loads(path.read_text(encoding='utf-8')) != candidate:
        profiles._write_replace(path, json.dumps(candidate, indent=2) + '\n')
    _save_keys(candidate, values)
    pending.unlink()
    return candidate
