"""One explicit desktop action; choose and revalidate existing launcher branches."""
import json
from pathlib import Path

from scripts.launcher import installation_profiles as profiles
from scripts.launcher.installation_permissions import require_private, require_unlinked
from scripts.launcher.installation_connection import (CONNECTION_FIELDS, ConnectionError, MissingProductionSettings,
                                                    update_connection)
from scripts.launcher.model import LauncherError
from scripts.launcher.process import check_cancelled


class Replan(Exception):
    """Release the old leases before selecting a different mutation branch."""

    def __init__(self, action):
        super().__init__(action)
        self.action = action


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


def _require_new_production_settings(args):
    if args.profile == 'prod':
        missing = [key for key in ('host', 'tls_cert_file', 'tls_key_file') if not getattr(args, key, None)]
        if missing:
            raise MissingProductionSettings(missing)


def connection_changes(profile, args):
    changes = {key: str(getattr(args, key)) if key.startswith('tls_') else getattr(args, key)
               for key in CONNECTION_FIELDS - {'port_modes'} if getattr(args, key, None) is not None}
    return {key: value for key, value in changes.items() if profile is None or value != profile.get(key)}


def _optional_changes(profile, args):
    if args.env_file and args.profile != 'dev':
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


def needs_preparation(project, args, *, before_lock=False, observed_runtime=None):
    """Read-only decision; an error is not permission to repair unknown state."""
    from scripts.launcher.validation_policy import require_validation_policy
    policy = require_validation_policy(getattr(args, 'validation_policy', 'managed'),
                                       profile=args.profile, source_selection=args.source_selection)
    developer = policy == 'developer'
    if observed_runtime is not None:
        observed_runtime.clear()
    path = _profile_path(args)
    for candidate in (path, path.with_name(args.profile + '.pending.json')):
        require_unlinked(candidate)
    if path.with_name(args.profile + '.pending.json').exists() or not path.exists():
        return True
    args.progress('Kayıtlı profil ve TLS dosya yolları denetleniyor' if args.profile == 'prod' else
                  'Kayıtlı profil denetleniyor')
    profile = profiles.load_profile(project, args.profile, tls_replacements=_tls_replacements(args))
    if any(profile.get('port_modes', {}).get(field) == 'automatic'
           for field in getattr(args, '_automatic_port_conflicts', ())):
        return True
    if args.profile == 'dev':
        from scripts.launcher.installation_local_config import configuration_changed
        connection_changed = configuration_changed(project, args, profile)
    else:
        connection_changed = bool(connection_changes(profile, args))
    if connection_changed or _optional_changes(profile, args):
        return True
    from scripts.launcher.installation_backup import has_unresolved_migration
    if has_unresolved_migration(profile):
        return True
    from scripts.launcher.installation import _core_checks, _runtime_options
    from scripts.launcher.toolchain import inspect_toolchain
    home, runtime_options = profiles.installation_home(), _runtime_options(profile)
    options = {'verify': False} if developer else {}
    runtime_paths = {}
    if runtime_options:
        options['observed_runtime'] = runtime_paths
    checks = [] if before_lock else inspect_toolchain(home, **runtime_options, **options)
    if any(row['status'] == 'invalid' for row in checks):
        raise LauncherError('Runtime bütünlüğü doğrulanamadı; kurulum otomatik değiştirilmedi.')
    if any(row['status'] != 'ready' for row in checks):
        return True
    # Keep the requested verification policy with the proof: developer checks
    # authorize only another identity/version check under these same leases.
    if not before_lock and observed_runtime is not None:
        observed_runtime.update(home=home, checks=[dict(row) for row in checks], verify=not developer,
                                **runtime_options, **runtime_paths)
    if not before_lock:
        args.progress('Geliştirici modu — bağımlılık kayıtları ve güncel şema denetleniyor' if developer else
                      'Kurulu Python ve frontend bağımlılıklarının dosyaları doğrulanıyor')
    state = {}
    options = {'validation_policy': 'developer'} if developer else {}
    checks.extend(_core_checks(project, profile, before_lock=before_lock, observed_backend=state,
                               fail_invalid=True, managed_build=True, **options))
    if state.get('schema') in {'ready', 'pending'} and state.get('auto_migrate_safe') is False:
        raise LauncherError('Veritabanı migration geçmişi otomatik hazırlık için doğrulanamadı.')
    return any(row['status'] not in {'ready', 'available'} for row in checks)


def _initial_action(args):
    from .operations import _project_for
    path = _profile_path(args)
    require_unlinked(path)
    if path.exists():
        return 'provision' if needs_preparation(_project_for('doctor', args, before_lock=True), args,
                                               before_lock=True) else 'start'
    pending = path.with_name(args.profile + '.pending.json')
    require_unlinked(pending)
    if not pending.exists():
        profiles.require_new_environment(path.with_name(args.profile + '.env'))
        _require_new_production_settings(args)
    return 'provision'


def run(args, emit):
    from .operations import _dispatch, _project_for
    from scripts.launcher.runtime import PortUnavailable
    args.manager_ensure = True
    resolve_source(args)
    action = None
    port_conflicts = branch_changes = 0
    while branch_changes < 3:
        check_cancelled()
        args.progress('Ortam ve uygulanacak ayarlar denetleniyor')
        if action is None:
            action = _initial_action(args)
        try:
            _dispatch(action, args, emit)
            return
        except Replan as change:
            branch_changes += 1
            action = change.action  # Revalidate under the newly acquired leases.
        except PortUnavailable as error:
            if args.profile != 'dev':
                raise ConnectionError('backend_port', occupied=True) from None
            port_conflicts += 1
            project = _project_for('doctor', args)
            profile = profiles.load_profile(project, args.profile)
            field = next((key for key in ('backend_port', 'frontend_port') if profile[key] == error.port), None)
            if not field or profile.get('port_modes', {}).get(field) != 'automatic' or port_conflicts >= 3:
                raise ConnectionError(field or 'backend_port', occupied=True) from None
            args._automatic_port_conflicts = (field,)
            args.progress('Otomatik port kullanılıyor; boş port yeniden seçiliyor')
            action = None
    raise LauncherError('Profil işlem sırasında değişti; yeniden deneyin.')


def prepare_connection(project, args):
    """Called only under preparation leases, before dependent provision steps."""
    home, path, env = profiles._paths(project, args.profile, None)
    pending = path.with_name(args.profile + '.pending.json')
    if args.profile == 'dev':
        from scripts.launcher.installation_local_config import apply_local_configuration
        previous = {}
        for file in (path, env):
            require_unlinked(file)
            if file.exists():
                require_private(file)
                previous[file] = file.read_bytes()
        updated = apply_local_configuration(project, args)
        args._automatic_port_conflicts = ()
        args.local_configuration = True
        args.port_modes = updated['port_modes']
        return path in previous and any(previous.get(file) != file.read_bytes() for file in (path, env))
    profiles._recover_pending(project, args.profile, home, path, env, pending)
    profile = profiles.load_profile(project, args.profile, tls_replacements=_tls_replacements(args)) if path.exists() else None
    changes = connection_changes(profile, args)
    if profile is None:
        profiles.require_new_environment(env)
        _require_new_production_settings(args)
        args.automatic_ports = tuple(key for key, mode in changes.get('port_modes', {}).items()
                                     if mode == 'automatic')
        for field, value in changes.items():
            setattr(args, field, value)
        return False
    candidate = {**profile, **changes}
    profiles._validate_options(candidate)
    if args.profile == 'prod' and changes:
        from scripts.launcher.installation import _tls_preflight
        args.progress('Seçilen TLS sertifikası, özel anahtar ve IPv4 eşleşmesi doğrulanıyor')
        _tls_preflight(project, candidate)
    if args.env_file:
        from scripts.launcher.installation_env import read_selected_environment, merge_selected_environment
        from scripts.launcher.installation_connection import connection_environment
        selected = read_selected_environment(project, args.profile, args.env_file)
        current = connection_environment(profile, candidate, profiles.read_profile_environment(profile))
        merge_selected_environment(candidate, current, selected, existing=True)
    if changes:
        update_connection(project, profile, changes)
    return bool(changes)


def claimed(project, action, args, emit):
    """The branch decision is revalidated after its OS-owned leases are acquired."""
    observed_runtime = {}
    required = 'provision' if needs_preparation(project, args, observed_runtime=observed_runtime) else 'start'
    if action != required:
        raise Replan(required)
    emit({'type': 'resources', 'action': action, 'source_root': str(project.root),
          'validation_policy': getattr(args, 'validation_policy', 'managed')})
    if action == 'provision':
        updated = prepare_connection(project, args)
        if updated and not needs_preparation(project, args, observed_runtime=observed_runtime):
            action = 'start'
    from .operations import _run_lifecycle
    if action == 'start' and observed_runtime:
        from scripts.launcher.toolchain import verified_toolchain_scope
        # These are the same leases used by the decision above. Provision may
        # change runtimes, so only the confirmed start branch can share proof.
        with verified_toolchain_scope(**observed_runtime):
            return _run_lifecycle(project, action, args, emit, ensured=True)
    _run_lifecycle(project, action, args, emit, ensured=True)
