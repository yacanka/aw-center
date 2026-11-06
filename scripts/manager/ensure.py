"""One explicit desktop action; choose and revalidate existing launcher branches."""
import json
from pathlib import Path

from scripts.launcher import installation_profiles as profiles
from scripts.launcher.installation_permissions import require_private, require_unlinked
from scripts.launcher.installation_connection import (CONNECTION_FIELDS, ConnectionError,
                                                    select_ports, update_connection)
from scripts.launcher.model import LauncherError
from scripts.launcher.process import check_cancelled


class Replan(Exception):
    """Release the old leases before selecting a different mutation branch."""


def resolve_source(args, home=None):
    """Saved canonical identity wins over media defaults, never explicit input."""
    if args.source_selection != 'automatic':
        return
    home = home if home is not None else profiles.installation_home()
    path = home / 'config' / (args.profile + '.profile.json')
    require_unlinked(path)
    if not path.exists():
        return
    for item in (home, path.parent, path):
        require_private(item)
    try:
        if path.stat().st_size > 64 * 1024:
            raise ValueError
        document = json.loads(path.read_text(encoding='utf-8'))
        source = document['source_root']
        if document['name'] != args.profile or not isinstance(source, str) or not Path(source).is_absolute():
            raise ValueError
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise LauncherError('Kayıtlı profil kaynağı doğrulanamadı.') from None
    # Full profile/env and packaged source validation follows before any write.
    args.source_root = source


def _profile_path(args):
    return profiles.installation_home() / 'config' / (args.profile + '.profile.json')


def _tls_replacements(args):
    return {key: str(getattr(args, key)) for key in profiles.TLS_PATH_FIELDS
            if getattr(args, key, None)}


def connection_changes(profile, args):
    changes = {key: str(getattr(args, key)) if key.startswith('tls_') else getattr(args, key)
               for key in CONNECTION_FIELDS - {'port_modes'} if getattr(args, key, None) is not None}
    if args.profile == 'dev':
        modes = (profile or {}).get('port_modes', {})
        if profile is None or getattr(args, 'automatic_ports', ()) or any(value == 'automatic' for value in modes.values()):
            changes.update(select_ports(profile, changes, automatic=getattr(args, 'automatic_ports', ())))
        elif any(key in changes for key in ('backend_port', 'frontend_port')):
            changes['port_modes'] = {key: 'manual' for key in ('backend_port', 'frontend_port')}
    return {key: value for key, value in changes.items() if profile is None or value != profile.get(key)}


def _optional_changes(profile, args):
    if args.env_file:
        from scripts.launcher.installation_env import read_selected_environment, merge_selected_environment
        from scripts.launcher.discovery import discover_project
        project = discover_project(Path(profile['source_root']))
        current = profiles.read_profile_environment(profile)
        selected = read_selected_environment(project, args.profile, args.env_file)
        if merge_selected_environment(profile, current, selected, existing=True) != current:
            return True
    if args.assets:
        from scripts.launcher.installation_bundle import verify_asset_source
        if verify_asset_source(args.assets)['asset_set'] != profile['asset_set']:
            return True
    if args.feature_catalog:
        from scripts.launcher.installation_features import read_feature_catalog
        installed = Path(profile['installation_home']) / 'config/features.catalog.json'
        if not installed.is_file() or read_feature_catalog(args.feature_catalog) != read_feature_catalog(installed):
            return True
    if any(getattr(args, key, None) for key in ('python_command', 'node_command', 'install_python', 'install_node')):
        from scripts.launcher.runtime_selection import tool_choices
        selected = tool_choices(args, profile)
        if any(str(selected.get(key) or '') != (profile.get(key) or '')
               for key in ('python_executable', 'node_executable')):
            return True
    return False


def needs_preparation(project, args):
    """Read-only decision; an error is not permission to repair unknown state."""
    path = _profile_path(args)
    for candidate in (path, path.with_name(args.profile + '.pending.json')):
        require_unlinked(candidate)
    if path.with_name(args.profile + '.pending.json').exists() or not path.exists():
        return True
    args.progress('Kayıtlı profil ve TLS dosya yolları denetleniyor' if args.profile == 'prod' else
                  'Kayıtlı profil denetleniyor')
    profile = profiles.load_profile(project, args.profile, tls_replacements=_tls_replacements(args))
    if connection_changes(profile, args) or _optional_changes(profile, args):
        return True
    from scripts.launcher.installation_backup import has_unresolved_migration
    if has_unresolved_migration(profile):
        return True
    from scripts.launcher.installation import _core_checks, _runtime_options, backend_inspection
    from scripts.launcher.toolchain import inspect_toolchain
    checks = inspect_toolchain(profiles.installation_home(), **_runtime_options(profile))
    if any(row['status'] == 'invalid' for row in checks):
        raise LauncherError('Runtime bütünlüğü doğrulanamadı; kurulum otomatik değiştirilmedi.')
    if project.python.is_file():
        state = backend_inspection(project, profile)
        if state.get('schema') in {'ready', 'pending'} and state.get('auto_migrate_safe') is False:
            raise LauncherError('Veritabanı migration geçmişi otomatik hazırlık için doğrulanamadı.')
    return any(row['status'] not in {'ready', 'available'}
               for row in checks + _core_checks(project, profile))


def run(args, emit):
    from .operations import _dispatch, _project_for
    from scripts.launcher.runtime import PortUnavailable
    args.manager_ensure = True
    resolve_source(args)
    for attempt in range(3):
        check_cancelled()
        args.progress('Ortam ve uygulanacak ayarlar denetleniyor')
        exists = _profile_path(args).exists()
        action = 'provision' if not exists else (
            'provision' if needs_preparation(_project_for('doctor', args), args) else 'start')
        try:
            _dispatch(action, args, emit)
            return
        except Replan:
            continue  # All old leases have been released by _dispatch.
        except PortUnavailable as error:
            if args.profile != 'dev' or attempt == 2:
                raise ConnectionError('backend_port', occupied=True) from None
            project = _project_for('doctor', args)
            profile = profiles.load_profile(project, args.profile)
            field = next((key for key in ('backend_port', 'frontend_port') if profile[key] == error.port), None)
            if not field or profile.get('port_modes', {}).get(field) != 'automatic':
                raise ConnectionError(field or 'backend_port', occupied=True) from None
            args.progress('Otomatik port kullanılıyor; boş port yeniden seçiliyor')
    raise LauncherError('Profil işlem sırasında değişti; yeniden deneyin.')


def prepare_connection(project, args):
    """Called only under preparation leases, before dependent provision steps."""
    home, path, env = profiles._paths(project, args.profile, None)
    pending = path.with_name(args.profile + '.pending.json')
    profiles._recover_pending(project, args.profile, home, path, env, pending)
    profile = profiles.load_profile(project, args.profile, tls_replacements=_tls_replacements(args)) if path.exists() else None
    changes = connection_changes(profile, args)
    if profile is None:
        if args.profile == 'prod':
            for field in ('host', 'tls_cert_file', 'tls_key_file'):
                if not getattr(args, field, None):
                    raise ConnectionError(field)
        args.automatic_ports = tuple(key for key, mode in changes.get('port_modes', {}).items()
                                     if mode == 'automatic')
        for field, value in changes.items():
            setattr(args, field, value)
        return
    candidate = {**profile, **changes}
    profiles._validate_options(candidate)
    if args.profile == 'prod' and changes:
        from scripts.launcher.installation import _tls_preflight
        from scripts.launcher.runtime import validate_tls_identity
        args.progress('Seçilen TLS sertifikası, özel anahtar ve IPv4 eşleşmesi doğrulanıyor')
        _tls_preflight(project, candidate)
        validate_tls_identity(project, Path(candidate['tls_cert_file']), Path(candidate['tls_key_file']), candidate['host'])
    if args.env_file:
        from scripts.launcher.installation_env import read_selected_environment, merge_selected_environment
        from scripts.launcher.installation_connection import connection_environment
        selected = read_selected_environment(project, args.profile, args.env_file)
        current = connection_environment(profile, candidate, profiles.read_profile_environment(profile))
        merge_selected_environment(candidate, current, selected, existing=True)
    if changes:
        update_connection(project, profile, changes)


def claimed(project, action, args, emit):
    """The branch decision is revalidated after its OS-owned leases are acquired."""
    if needs_preparation(project, args) != (action == 'provision'):
        raise Replan()
    emit({'type': 'resources', 'action': action, 'source_root': str(project.root)})
    if action == 'provision':
        prepare_connection(project, args)
    from .operations import _run_lifecycle
    _run_lifecycle(project, action, args, emit, ensured=True)
