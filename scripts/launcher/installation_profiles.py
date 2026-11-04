"""Explicit, private, user-scoped installation profiles; inspection never provisions."""

from __future__ import annotations

import base64
import hashlib
import tempfile
import json
import os
from pathlib import Path
import re
import secrets

from .installation_permissions import require_private, require_unlinked, secure_path
from .model import LauncherError


PROFILE_VERSION = 1
INSTALLER_ENVIRONMENT_KEYS = {
    'AWCENTER_MANAGED_PYTHON', 'AWCENTER_MANAGED_NODE', 'AWCENTER_MANAGED_NPM_CLI',
    'AWCENTER_PACKAGE_REPOSITORY', 'AWCENTER_OFFLINE_DIR',
}
RELEVANT_PREFIXES = (
    'AWCENTER_', 'DATABASE_', 'SQLITE_', 'PRIVATE_', 'CACHE_', 'JIRA_',
    'DOORS_', 'DOCPROOF_', 'NUMARATOR_', 'TEAMCENTER_', 'AI_API_', 'WORD_',
    'EMAIL_', 'SESSION_COOKIE_', 'CSRF_', 'SECURE_', 'DEV_', 'MODEL_',
    'CUSTOM_TEMPLATE_', 'COVER_PAGE_', 'FRONTEND_', 'TRUST_',
)
RELEVANT_KEYS = {
    'SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS', 'ALLOW_ALL_DEBUG_HOSTS',
    'IPV4_ADDRESS', 'PORT', 'STATIC_ROOT', 'MEDIA_ROOT', 'TRUSTED_PROXY_COUNT',
    'DJANGO_SETTINGS_MODULE', 'DB_OLD_URL',
}
PROFILE_BOUND_KEYS = {
    'DEBUG', 'AWCENTER_DEPLOYMENT_MODE', 'IPV4_ADDRESS', 'PORT',
    'DEV_BACKEND_PORT', 'DEV_FRONTEND_PORT', 'DATABASE_URL', 'PRIVATE_MEDIA_ROOT',
    'CACHE_DIRECTORY', 'STATIC_ROOT', 'MEDIA_ROOT', 'MODEL_RUNTIME_DIR',
    'CUSTOM_TEMPLATE_DIR', 'ALLOW_ALL_DEBUG_HOSTS', 'ALLOWED_HOSTS',
    'DATABASE_CONN_MAX_AGE', 'SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE',
    'CSRF_COOKIE_SECURE', 'TRUST_PROXY_HEADERS', 'TRUSTED_PROXY_COUNT',
}


def installation_home() -> Path:
    """Return the Windows per-user managed home, never a source-tree fallback."""
    local = os.environ.get('LOCALAPPDATA')
    if not local or not Path(local).is_absolute():
        raise LauncherError('LOCALAPPDATA must identify the current user application-data directory')
    return Path(local) / 'AWCenter'


def _paths(project, name, home):
    if name not in {'dev', 'prod'}:
        raise LauncherError('Installation profile must be dev or prod')
    home = Path(os.path.abspath(home if home is not None else installation_home()))
    require_unlinked(home)
    if home.resolve().is_relative_to(project.root.resolve()):
        raise LauncherError('Installation configuration must be outside the source checkout')
    return home, home / 'config' / f'{name}.profile.json', home / 'config' / f'{name}.env'


def read_environment(path: Path) -> dict[str, str]:
    """Read private runtime dotenv data, without modifying os.environ."""
    require_private(path)
    try:
        return parse_environment(path.read_text(encoding='utf-8'))
    except UnicodeError:
        raise LauncherError('Private environment file is invalid; values have been withheld') from None


def parse_environment(content: str) -> dict[str, str]:
    """Parse literal dotenv values; never interpolate variables or execute code."""
    result = {}
    try:
        lines = content.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, separator, value = line.partition('=')
            key, value = key.strip(), value.strip()
            if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in result:
                raise ValueError
            if value.startswith('"'):
                value = json.loads(value)
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            if not isinstance(value, str) or '\n' in value or '\r' in value or '\x00' in value:
                raise ValueError
            result[key] = value
    except (OSError, UnicodeError, ValueError):
        raise LauncherError('Private environment file is invalid; values have been withheld') from None
    return result


def read_profile_environment(profile) -> dict[str, str]:
    """Read private configuration for internal inspection only; never log this mapping."""
    return read_environment(Path(profile['env_file']))


def _configuration(profile):
    home = Path(profile['installation_home'])
    source = Path(profile['source_root'])
    production = profile['name'] == 'prod'
    state = home / 'state' / 'production' if production else source / 'backend'
    host, backend, frontend = profile['host'], profile['backend_port'], profile['frontend_port']
    origin = f'http://{host}:{frontend}'
    if production:
        origin = f'https://{host}' + (f':{backend}' if backend != 443 else '')
    values = {
        'DEBUG': str(not production),
        'AWCENTER_DEPLOYMENT_MODE': 'windows-native' if production else 'development',
        'IPV4_ADDRESS': host,
        'PORT': str(backend),
        'DEV_BACKEND_PORT': str(backend),
        'DEV_FRONTEND_PORT': str(frontend),
        'ALLOWED_HOSTS': host if production else '127.0.0.1,localhost',
        'ALLOW_ALL_DEBUG_HOSTS': 'False',
        'DATABASE_URL': 'sqlite:///' + (state / 'db.sqlite3').as_posix(),
        'DATABASE_CONN_MAX_AGE': '0',
        'SQLITE_BUSY_TIMEOUT_SECONDS': '30',
        'PRIVATE_MEDIA_ROOT': (state / 'private_media').as_posix(),
        'CACHE_URL': '', 'CACHE_DIRECTORY': (state / 'cache').as_posix() if production else '',
        'CSRF_TRUSTED_ORIGINS': origin if production else ','.join(
            f'http://{address}:{port}'
            for port in (frontend, backend)
            for address in ('127.0.0.1', 'localhost')
        ),
        'SECURE_SSL_REDIRECT': str(production),
        'SECURE_HSTS_SECONDS': '31536000' if production else '0',
        'TRUST_PROXY_HEADERS': 'False', 'TRUSTED_PROXY_COUNT': '0',
        'SESSION_COOKIE_SECURE': str(production), 'CSRF_COOKIE_SECURE': str(production),
        'AWCENTER_MAIL_TRANSPORT': 'disabled', 'JIRA_ENABLED': 'False', 'DOCPROOF_ENABLED': 'False',
        'TEAMCENTER_ENABLED': 'False', 'NUMARATOR_ENABLED': 'False', 'DOORS_ENABLED': 'False',
        'JIRA_VERIFY_SSL': 'True', 'DOCPROOF_VERIFY_SSL': 'True', 'NUMARATOR_VERIFY_SSL': 'True',
        'MODEL_RUNTIME_DIR': (home / 'assets' / 'sets' / profile['asset_set'] / 'ai-models').as_posix(),
        'CUSTOM_TEMPLATE_DIR': (home / 'assets' / 'sets' / profile['asset_set'] / 'document-templates').as_posix(),
        'FRONTEND_RESET_URL': origin + '/app/login',
        'FRONTEND_INVITATION_URL': origin + '/app/invite',
    }
    if production:
        values.update(STATIC_ROOT=(state / 'staticfiles').as_posix(), MEDIA_ROOT=(state / 'media').as_posix())
    else:
        values['DEV_SERVER_ORIGINS'] = values['CSRF_TRUSTED_ORIGINS']
    return values


def _validate_options(profile):
    for field in ('python_executable', 'node_executable'):
        executable = profile.get(field)
        if executable is not None and (not isinstance(executable, str) or not Path(executable).is_absolute()
                                       or any(char in executable for char in '\r\n\0')):
            raise LauncherError('System runtime pointer must be an absolute executable path')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', profile['asset_set']) or profile['asset_set'] in {'.', '..'}:
        raise LauncherError('Asset set must be a simple reviewed identifier')
    for key in ('backend_port', 'frontend_port'):
        if isinstance(profile[key], bool) or not isinstance(profile[key], int) or not 1 <= profile[key] <= 65535:
            raise LauncherError('Profile ports must be integers between 1 and 65535')
    if profile['name'] == 'dev':
        if profile['host'] != '127.0.0.1':
            raise LauncherError('Development profile must bind to 127.0.0.1')
        if profile['backend_port'] == profile['frontend_port']:
            raise LauncherError('Development frontend and backend ports must differ')
        return
    source = Path(profile['source_root'])
    require_unlinked(source)
    require_unlinked(source / '.venv')
    try:
        release = source.relative_to(Path(profile['installation_home']) / 'releases')
    except ValueError:
        raise LauncherError('Production requires a separate release under installation home/releases/<release-id>/source') from None
    if len(release.parts) != 2 or release.parts[-1] != 'source' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', release.parts[0]):
        raise LauncherError('Production requires a separate release under installation home/releases/<release-id>/source')
    from .runtime import require_production_host
    require_production_host(profile['host'])
    for key in ('tls_cert_file', 'tls_key_file'):
        if not profile.get(key):
            raise LauncherError('Production requires operator-supplied TLS certificate and private key')
        path = Path(profile[key])
        require_unlinked(path)
        if not path.is_absolute() or not path.is_file() or path.resolve().is_relative_to(Path(profile['source_root']).resolve()):
            raise LauncherError('Production TLS files must be existing external regular files')


def _validate_environment(profile, values):
    expected = _configuration(profile)
    if any(values.get(key) != expected.get(key) for key in PROFILE_BOUND_KEYS if key in expected):
        raise LauncherError('Profile environment conflicts with its isolated state, bind or asset paths')
    asset_models = Path(expected['MODEL_RUNTIME_DIR'])
    asset_templates = Path(expected['CUSTOM_TEMPLATE_DIR'])
    optional_asset_paths = {
        'WORD_TRANSLATION_TR_EN_MODEL': asset_models / 'opus-mt-tr-en',
        'WORD_TRANSLATION_EN_TR_MODEL': asset_models / 'opus-mt-en-tr',
        'WORD_ANALYZER_BI_MODEL': asset_models / 'paraphrase-multilingual',
        'WORD_ANALYZER_CROSS_MODEL': asset_models / 'ms-marco-cross-encoder',
        'COVER_PAGE_TEMPLATE_PATH': asset_templates / 'cover_page_template.docx',
    }
    for key, path in optional_asset_paths.items():
        if key in values and values[key] != path.as_posix():
            raise LauncherError('Model and template overrides must use the selected canonical asset set')
        require_unlinked(path)
    if not values.get('SECRET_KEY', '').strip():
        raise LauncherError('Profile requires an explicit SECRET_KEY')
    try:
        if len(base64.b64decode(values.get('JIRA_SESSION_ENCRYPTION_KEY', ''), altchars=b'-_', validate=True)) != 32:
            raise ValueError
    except ValueError:
        raise LauncherError('Profile requires a separately generated valid JIRA encryption key') from None
    for key in ('DATABASE_URL', 'PRIVATE_MEDIA_ROOT', 'CACHE_DIRECTORY', 'MODEL_RUNTIME_DIR', 'CUSTOM_TEMPLATE_DIR', 'STATIC_ROOT', 'MEDIA_ROOT'):
        value = values.get(key, '')
        if value:
            require_unlinked(Path(value.removeprefix('sqlite:///')))


def _require_separate(home, name, values, source_root):
    other = home / 'config' / ('prod.env' if name == 'dev' else 'dev.env')
    require_unlinked(other)
    if not other.exists():
        return
    other_values = read_environment(other)
    other_profile = other.with_suffix('.profile.json')
    require_unlinked(other_profile)
    if other_profile.exists():
        require_private(other_profile)
        try:
            other_data = json.loads(other_profile.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError):
            raise LauncherError('The other installation profile is invalid') from None
        if not isinstance(other_data, dict) or other_data.get('source_root') == source_root:
            raise LauncherError('Development and production must use separate source roots and virtual environments')
    for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY', 'DATABASE_URL', 'PRIVATE_MEDIA_ROOT', 'CACHE_DIRECTORY'):
        if values.get(key) and values.get(key) == other_values.get(key):
            raise LauncherError('Development and production must not share secrets or state')


def load_profile(project, name, home=None) -> dict:
    """Load and validate a profile without creating files or repairing permissions."""
    home, path, env = _paths(project, name, home)
    try:
        require_private(home)
        require_private(path.parent)
        require_private(path)
        profile = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(profile, dict) or profile.get('version') != PROFILE_VERSION:
            raise LauncherError('Unsupported installation profile version')
        if profile.get('name') != name or profile.get('source_root') != str(project.root.resolve()):
            raise LauncherError('Installation profile belongs to a different source checkout')
        if profile.get('env_file') != str(env) or profile.get('installation_home') != str(home):
            raise LauncherError('Installation profile environment pointer is invalid')
        _validate_options(profile)
        values = read_environment(env)
        _validate_environment(profile, values)
        _require_separate(home, name, values, profile['source_root'])
        return profile
    except FileNotFoundError:
        raise LauncherError('Installation profile is missing; run explicit provisioning first') from None
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise LauncherError('Installation profile is invalid; configuration values have been withheld') from None


def _create_private_directory(path):
    if path.exists():
        require_private(path)
        return
    if not path.parent.exists():
        _create_private_directory(path.parent)
    path.mkdir(mode=0o700)
    secure_path(path)


def _atomic_write(path, content, *, replace):
    """Publish a fully fsynced owner-only file; create never overwrites a file."""
    require_unlinked(path)
    if replace:
        require_private(path)
    descriptor, name = tempfile.mkstemp(prefix='.profile-write-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            secure_path(temporary)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Hard-link publication is atomic and fails when the destination
            # exists on both local NTFS and POSIX, unlike POSIX rename().
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_new(path, content):
    _atomic_write(path, content, replace=False)


def _write_replace(path, content):
    _atomic_write(path, content, replace=True)


def _environment_content(values):
    return ''.join(f'{key}={json.dumps(value, ensure_ascii=False)}\n' for key, value in values.items())


def _digest(content):
    return hashlib.sha256(content if isinstance(content, bytes) else content.encode('utf-8')).hexdigest()


def _asset_values(profile, values):
    result = dict(values)
    models = Path(profile['installation_home']) / 'assets/sets' / profile['asset_set'] / 'ai-models'
    templates = models.parent / 'document-templates'
    result.update(MODEL_RUNTIME_DIR=models.as_posix(), CUSTOM_TEMPLATE_DIR=templates.as_posix(),
                  WORD_TRANSLATION_TR_EN_MODEL=(models / 'opus-mt-tr-en').as_posix(),
                  WORD_TRANSLATION_EN_TR_MODEL=(models / 'opus-mt-en-tr').as_posix(),
                  WORD_ANALYZER_BI_MODEL=(models / 'paraphrase-multilingual').as_posix(),
                  WORD_ANALYZER_CROSS_MODEL=(models / 'ms-marco-cross-encoder').as_posix(),
                  COVER_PAGE_TEMPLATE_PATH=(templates / 'cover_page_template.docx').as_posix())
    return result


def _pending_metadata(profile, values, *, operation, previous_environment=None, previous_profile=None):
    document = {'version': 1, 'operation': operation, 'profile': profile,
                'environment_sha256': _digest(_environment_content(values))}
    if previous_environment is not None:
        document['previous_environment_sha256'] = _digest(previous_environment)
        document['previous_profile_sha256'] = _digest(previous_profile)
    return json.dumps(document, indent=2) + '\n'


def _recover_pending(project, name, home, path, env, pending):
    """Only explicit provisioning resumes our private, hash-bound transaction."""
    if not pending.exists():
        return None
    require_private(home)
    require_private(pending.parent)
    require_private(pending)
    try:
        if pending.stat().st_size > 64 * 1024:
            raise ValueError
        document = json.loads(pending.read_text(encoding='utf-8'))
        candidate = document['profile']
        if (document['version'] != 1 or document['operation'] not in {'create', 'assets'} or
                candidate['version'] != PROFILE_VERSION or candidate['name'] != name or
                candidate['source_root'] != str(project.root.resolve()) or
                candidate['installation_home'] != str(home) or candidate['env_file'] != str(env)):
            raise ValueError
        _validate_options(candidate)
        if not env.exists():
            if path.exists() or document['operation'] != 'create':
                raise ValueError
            return candidate  # No environment was published, so fresh keys are safe.
        require_private(env)
        current_digest = _digest(env.read_bytes())
        if document['operation'] == 'assets' and current_digest == document.get('previous_environment_sha256'):
            if not path.exists() or _digest(path.read_bytes()) != document['previous_profile_sha256']:
                raise ValueError
            values = _asset_values(candidate, read_environment(env))
            content = _environment_content(values)
            if _digest(content) != document['environment_sha256']:
                raise ValueError
            _validate_environment(candidate, values)
            _require_separate(home, name, values, candidate['source_root'])
            _check_inherited(values, str(env))
            _write_replace(env, content)
        elif current_digest != document['environment_sha256']:
            raise ValueError
        values = read_environment(env)
        _validate_environment(candidate, values)
        _require_separate(home, name, values, candidate['source_root'])
        _check_inherited(values, str(env))
        if path.exists():
            require_private(path)
            current = json.loads(path.read_text(encoding='utf-8'))
            if current != candidate:
                if document['operation'] != 'assets' or _digest(path.read_bytes()) != document['previous_profile_sha256']:
                    raise ValueError
                _write_replace(path, json.dumps(candidate, indent=2) + '\n')
        else:
            _write_new(path, json.dumps(candidate, indent=2) + '\n')
        pending.unlink()
        return candidate
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise LauncherError('Pending installation metadata does not match existing configuration; recover manually without replacing keys') from None


def _reject_existing_manual_configuration(project):
    database = project.backend / 'db.sqlite3'
    manual = any((project.backend / name).exists() for name in ('.env', '.env.local', 'production.env'))
    inherited = os.environ.get('AWCENTER_ENV_FILE')
    if database.exists() and (manual or (inherited and Path(inherited).is_file())):
        raise LauncherError('Existing database and manual environment require explicit configuration adoption; keys were not replaced')


def provision_profile(project, name, home=None, **options) -> dict:
    """Create private keys/config once. Existing configuration is never overwritten."""
    home, path, env = _paths(project, name, home)
    selected = None
    if options.get('env_file'):
        from .installation_env import read_selected_environment
        selected = read_selected_environment(project, name, Path(options['env_file']))
    require_unlinked(path)
    require_unlinked(env)
    pending = path.with_name(name + '.pending.json')
    require_unlinked(pending)
    recovered = _recover_pending(project, name, home, path, env, pending)
    if path.exists():
        profile = load_profile(project, name, home)
        if selected is not None:
            from .installation_env import import_selected_environment
            import_selected_environment(profile, selected)
        return load_profile(project, name, home)
    if env.exists():
        raise LauncherError('An existing environment has no profile; recover it manually without replacing keys')
    if selected is None:
        _reject_existing_manual_configuration(project)
    elif (project.backend / 'db.sqlite3').exists() and not all(selected.get(key, '').strip() for key in ('SECRET_KEY', 'JIRA_SESSION_ENCRYPTION_KEY')):
        raise LauncherError('Mevcut veritabanının .env dosyası her iki mevcut anahtarı da içermelidir; yeni anahtar üretilmedi.')
    profile = recovered or {
        'version': PROFILE_VERSION, 'name': name, 'source_root': str(project.root.resolve()),
        'installation_home': str(home), 'env_file': str(env),
        'host': options.get('host') or ('127.0.0.1' if name == 'dev' else ''),
        'backend_port': options.get('backend_port') if options.get('backend_port') is not None else (8000 if name == 'dev' else 443),
        'frontend_port': options.get('frontend_port') if options.get('frontend_port') is not None else 5173,
        'tls_cert_file': str(options['tls_cert_file']) if options.get('tls_cert_file') else None,
        'tls_key_file': str(options['tls_key_file']) if options.get('tls_key_file') else None,
        'asset_set': options.get('asset_set') or 'default',
        'exclude_doors': bool(options.get('exclude_doors', False)),
    }
    _validate_options(profile)
    values = _configuration(profile)
    values['SECRET_KEY'] = secrets.token_urlsafe(64)
    values['JIRA_SESSION_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii')
    if selected is not None:
        from .installation_env import merge_selected_environment
        values = merge_selected_environment(profile, values, selected, existing=False)
    _validate_environment(profile, values)
    _require_separate(home, name, values, profile['source_root'])
    # Conflict detection happens before any private files or directories are created.
    _check_inherited(values, str(env))
    _create_private_directory(home)
    _create_private_directory(path.parent)
    if name == 'prod':
        state = home / 'state' / 'production'
        _create_private_directory(state)
        for directory in ('private_media', 'cache', 'staticfiles', 'media'):
            _create_private_directory(state / directory)
    metadata = _pending_metadata(profile, values, operation='create')
    if pending.exists():
        _write_replace(pending, metadata)
    else:
        _write_new(pending, metadata)
    _write_new(env, _environment_content(values))
    _write_new(path, json.dumps(profile, indent=2) + '\n')
    pending.unlink()
    return load_profile(project, name, home)


def update_python_runtime(project, profile, python_executable: Path | None) -> dict:
    """Persist the explicitly selected interpreter without rewriting env/keys.

    Caller holds the installation lock and has verified the venv's base. Older
    profiles without this field retain their reviewed managed Python contract.
    """
    return _update_runtime(project, profile, 'python_executable', python_executable)


def update_node_runtime(project, profile, node_executable: Path | None) -> dict:
    """Persist a validated Node pointer under the installation lock; keep env/keys."""
    return _update_runtime(project, profile, 'node_executable', node_executable)


def _update_runtime(project, profile, field, executable):
    home, path, _ = _paths(project, profile['name'], profile['installation_home'])
    current = load_profile(project, profile['name'], home)
    if current != profile:
        raise LauncherError('Installation profile changed; reload before updating runtime')
    updated = dict(current)
    if executable is None:
        updated.pop(field, None)
    else:
        updated[field] = str(executable)
    _validate_options(updated)
    if updated != current:
        _write_replace(path, json.dumps(updated, indent=2) + '\n')
    return load_profile(project, profile['name'], home)


def update_asset_set(project, profile, asset_set) -> dict:
    """Rebind an explicitly imported approved set while retaining all other values.

    The caller validates/imports the immutable asset set first. A private pending
    journal lets explicit provisioning finish a write interrupted between files.
    """
    home, path, env = _paths(project, profile['name'], profile['installation_home'])
    pending = path.with_name(profile['name'] + '.pending.json')
    require_unlinked(pending)
    _recover_pending(project, profile['name'], home, path, env, pending)
    current = load_profile(project, profile['name'], home)
    if current['asset_set'] == asset_set:
        return current
    if current != profile:
        raise LauncherError('Installation profile changed; reload before updating its asset set')
    updated = {**current, 'asset_set': asset_set}
    _validate_options(updated)
    values = _asset_values(updated, read_environment(env))
    _validate_environment(updated, values)
    _require_separate(home, profile['name'], values, current['source_root'])
    _check_inherited(values, str(env))
    metadata = _pending_metadata(updated, values, operation='assets',
                                 previous_environment=env.read_bytes(), previous_profile=path.read_bytes())
    _write_new(pending, metadata)
    _write_replace(env, _environment_content(values))
    _write_replace(path, json.dumps(updated, indent=2) + '\n')
    pending.unlink()
    return load_profile(project, profile['name'], home)


def _check_inherited(values, env_file):
    for key, value in os.environ.items():
        if key in INSTALLER_ENVIRONMENT_KEYS:
            continue
        if key == 'AWCENTER_ENV_FILE':
            expected = env_file
        elif key == 'DJANGO_SETTINGS_MODULE':
            expected = 'awcenter.settings'
        elif key in values or key in RELEVANT_KEYS or key.startswith(RELEVANT_PREFIXES):
            expected = values.get(key)
        else:
            continue
        if value != expected:
            raise LauncherError(f'Inherited environment conflicts with installation profile: {key}; remove the override before continuing')


def profile_environment(profile) -> dict[str, str]:
    """Return child-only settings after refusing inherited setting/credential conflicts."""
    values = read_profile_environment(profile)
    _validate_environment(profile, values)
    _require_separate(Path(profile['installation_home']), profile['name'], values, profile['source_root'])
    _check_inherited(values, profile['env_file'])
    return {**values, 'AWCENTER_ENV_FILE': profile['env_file'], 'DJANGO_SETTINGS_MODULE': 'awcenter.settings'}


def inspect_profile(project, profile) -> list[dict]:
    """Report private profile readiness without creating storage, keys or databases."""
    try:
        home = profile.get('installation_home')
        if not Path(profile['env_file']).exists():
            return [{'name': 'profile', 'status': 'missing', 'detail': 'Run explicit profile provisioning.'}]
        loaded = load_profile(project, profile['name'], home)
        profile_environment(loaded)
    except (LauncherError, OSError, KeyError):
        return [{'name': 'profile', 'status': 'error', 'detail': 'Profile validation failed; verify ownership, paths and inherited environment.'}]
    return [{'name': 'profile', 'status': 'ready', 'detail': 'Private profile and isolated settings validated.'}]
