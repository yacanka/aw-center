"""Run a desktop profile against the operator's selected source and environment."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time

from scripts.launcher import installation_profiles as profiles
from scripts.launcher import process, runtime
from scripts.launcher.installation_backup import has_unresolved_migration, run_backed_up_migrations
from scripts.launcher.installation_env import read_application_environment
from scripts.launcher.installation_local_config import IDENTITY_KEYS, _database_identity, _identity_file, _read_keys
from scripts.launcher.installation_permissions import require_unlinked, secure_path
from scripts.launcher.installation_readiness import probe_http
from scripts.launcher.installation_state import installation_lock, private_directory, process_environment
from scripts.launcher.job_worker import start_job_workers, worker_has_startup_marker
from scripts.launcher.model import LauncherError
from .profile_state import claim_storage, sqlite_path as _sqlite_path, sqlite_url as _sqlite_url


def _selected(values):
    path = values.get('env_file')
    return read_application_environment(Path(path).expanduser().absolute()) if path else {}


def _fields(profile, source):
    keys = {
        'host': ('IPV4_ADDRESS',),
        'backend_port': ('PORT', 'DEV_BACKEND_PORT') if profile == 'prod' else ('DEV_BACKEND_PORT', 'PORT'),
        'frontend_port': ('DEV_FRONTEND_PORT',),
        'tls_cert_file': ('TLS_CERT_FILE',),
        'tls_key_file': ('TLS_KEY_FILE',),
    }
    result = {}
    for field, names in keys.items():
        for name in names:
            if name in source:
                result[field] = source[name]
                break
    return result


def env_fields(values):
    """Return only explicitly selected connection fields safe to display."""
    return _fields(values['profile'], _selected(values))


def _connection(values, selected):
    profile = values['profile']
    tls = profiles.installation_home() / 'tls' / profile
    result = {'host': '' if profile == 'prod' else '127.0.0.1', 'backend_port': 443 if profile == 'prod' else 8000,
              'frontend_port': 5173, 'tls_cert_file': str(tls / 'server.crt'),
              'tls_key_file': str(tls / 'server.key')}
    result.update({field: values[field] for field in result if values.get(field)})
    result.update(_fields(profile, selected))
    if profile == 'prod':
        result['frontend_port'] = 5173  # No Vite listener in this topology.
    for field in ('backend_port', 'frontend_port'):
        try:
            result[field] = int(result[field])
            if not 1 <= result[field] <= 65535:
                raise ValueError
        except (ValueError, TypeError):
            raise LauncherError('Port 1 ile 65535 arasında olmalıdır.') from None
    for field in ('tls_cert_file', 'tls_key_file'):
        if not result[field]:
            continue
        path = Path(result[field]).expanduser()
        if not path.is_absolute():
            path = Path(values['source_root']) / 'backend' / path
        result[field] = str(path.absolute())
    return result


def effective_connection(values):
    return _connection(values, _selected(values))


def _settings(project, values, connection, selected):
    home = profiles.installation_home()
    name = values['profile']
    legacy = home / 'config' / (name + '.env')
    stored = profiles.read_environment(legacy) if legacy.is_file() else {}
    profile = {**connection, 'name': name, 'source_root': str(project.root),
               'installation_home': str(home), 'asset_set': 'default'}
    base = profiles._configuration(profile)
    base['DATABASE_URL'] = _sqlite_url(Path(base['DATABASE_URL'][len('sqlite:///'):]))
    # Saved settings provide continuity for installed profiles. An explicit
    # source is authoritative and never inherits old optional integrations.
    fallback = stored if not values.get('env_file') else {
        key: stored[key] for key in ('DATABASE_URL', 'PRIVATE_MEDIA_ROOT', 'CACHE_DIRECTORY',
                                    'STATIC_ROOT', 'MEDIA_ROOT', 'MODEL_RUNTIME_DIR',
                                    'CUSTOM_TEMPLATE_DIR') if key in stored}
    settings = {**base, **fallback, **selected}
    host, port = connection['host'], connection['backend_port']
    for derived in ('ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'DEV_SERVER_ORIGINS',
                    'FRONTEND_RESET_URL', 'FRONTEND_INVITATION_URL'):
        if derived in base and derived not in selected:
            settings[derived] = base[derived]
    settings.update(IPV4_ADDRESS=host, PORT=str(port), DEV_BACKEND_PORT=str(port),
                    DEV_FRONTEND_PORT=str(connection['frontend_port']))
    if name == 'dev' and not selected.get('DEV_SERVER_ORIGINS'):
        origins = list(dict.fromkeys(f'http://{address}:{number}'
                      for address in ('localhost', '127.0.0.1', host)
                      for number in (connection['frontend_port'], port)))
        settings['DEV_SERVER_ORIGINS'] = ','.join(origins)
        if 'CSRF_TRUSTED_ORIGINS' not in selected:
            settings['CSRF_TRUSTED_ORIGINS'] = settings['DEV_SERVER_ORIGINS']
        if 'ALLOWED_HOSTS' not in selected:
            settings['ALLOWED_HOSTS'] = ','.join(dict.fromkeys(('localhost', '127.0.0.1', host)))
    database = _sqlite_path(project.backend, settings['DATABASE_URL'])
    # Settings are passed directly to each child. An empty selection must
    # never cause Django to read another implicit dotenv inside the checkout.
    settings.update(DATABASE_URL=_sqlite_url(database),
                    AWCENTER_ENV_FILE=os.devnull, DJANGO_SETTINGS_MODULE='awcenter.settings',
                    AWCENTER_MANAGED_PYTHON=str(project.python))
    return settings, database, stored


def _identity(project, home, database, settings, stored):
    identity = _database_identity(database)
    missing = [key for key in IDENTITY_KEYS if not settings.get(key)]
    if not missing:
        return
    known = _read_keys(home, identity)
    if stored.get('DATABASE_URL') and _sqlite_path(project.backend, stored['DATABASE_URL']) == database:
        known.update({key: stored[key] for key in IDENTITY_KEYS if stored.get(key)})
    for key in missing:
        if known.get(key):
            settings[key] = known[key]
    missing = [key for key in missing if not settings.get(key)]
    if not missing:
        return
    if database.exists():
        if 'SECRET_KEY' in missing or settings.get('JIRA_ENABLED', '').lower() in ('1', 'true', 'yes', 'on'):
            raise LauncherError('Mevcut veritabanının kimlik anahtarlarını içeren .env dosyasını seçin.')
        return
    for key in missing:
        settings[key] = (secrets.token_urlsafe(64) if key == 'SECRET_KEY' else
                         base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'))
    path = _identity_file(home, identity)
    private_directory(path.parent)
    try:
        profiles._write_new(path, profiles._environment_content({key: settings[key] for key in IDENTITY_KEYS}))
    except FileExistsError:
        # Another profile may have selected this new database at the same time.
        known = _read_keys(home, identity)
        for key in missing:
            settings[key] = known[key]


def _command(command, cwd, settings, label, *, payload=None, timeout=180, failure=None, safe_boundary=False):
    outcome = process.controlled_run([str(item) for item in command], cwd=cwd,
                env=process.environment(settings), input=payload, text=True, encoding='utf-8', errors='replace',
                capture_output=True, timeout=timeout, safe_boundary=safe_boundary)
    if outcome.returncode:
        detail = failure(outcome) if failure else ''
        raise LauncherError(label + (' ' + detail if detail else ''))
    return outcome


def _django(project, settings, args, *, timeout=180):
    from .profile_diagnostics import django_failure
    role = {**process.non_notification_environment(), 'NUMARATOR_API_KEY': ''}
    if args == ['check', '--deploy']:
        # The transport and TLS flags are validatable without the SMTP login.
        role.pop('AWCENTER_MAIL_TRANSPORT')
        for name in ('USERNAME', 'PASSWORD'):
            shared = 'AWCENTER_' + name
            role[shared] = ''
            for provider in ('DOCPROOF', 'DOORS', 'TEAMCENTER'):
                key = provider + '_' + name
                role[key] = settings.get(key) or settings.get(shared, '')
    env = {**settings, **role}
    command = [project.python, project.manage_py]
    def failure(outcome):
        if args == ['migrate', '--check']:
            plan = process.controlled_run([str(item) for item in [*command, 'showmigrations', '--plan']],
                       cwd=project.backend, env=process.environment(env), capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=timeout)
            pending = re.findall(r'^\[ \]\s+([A-Za-z][\w]*\.\d{4}_[A-Za-z0-9_]+)\s*$', plan.stdout, re.M)
            if pending:
                return 'Bekleyen migration: ' + ', '.join(pending)
        return django_failure(args[0], outcome.stderr, settings)
    _command([*command, *args], project.backend, env, f'Django komutu başarısız: {" ".join(args)}.',
             timeout=timeout, failure=failure, safe_boundary=args == ['migrate', '--noinput'])


def _first_database(project, database, settings, ask, notify):
    if database.exists():
        if not database.is_file():
            raise LauncherError('Veritabanı yolu normal bir dosya olmalıdır.')
        return
    if any(database.with_name(database.name + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise LauncherError('SQLite günlük dosyası mevcut, ana veritabanı dosyası eksik. Veritabanı yedeğini kontrol edin.')
    credentials = ask()
    if not credentials:
        raise process.OperationCancelled('İlk yönetici oluşturma iptal edildi.')
    database.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a fully migrated database with its first administrator.
    # A sibling temp directory keeps the atomic link on the same filesystem.
    with tempfile.TemporaryDirectory(prefix='.awcenter-init-', dir=database.parent) as temp:
        stage = Path(temp) / 'db.sqlite3'
        stage.touch(mode=0o600)
        secure_path(stage)
        env = {**settings, 'DATABASE_URL': _sqlite_url(stage)}
        notify('phase', 'Yeni SQLite veritabanı hazırlanıyor.')
        _django(project, env, ['migrate', '--noinput'], timeout=1800)
        from scripts.launcher.installation_probe import ADMIN_INPUT_ERRORS
        def rejection(outcome):
            try:
                code = json.loads(outcome.stdout).get('code')
            except (ValueError, AttributeError):
                return ''
            return ADMIN_INPUT_ERRORS.get(code, ('', 'Kullanıcı adı ve parolayı kontrol edin.'))[1]
        _command([project.python, '-m', 'scripts.launcher.installation_probe', 'initial-admin-json'],
                 project.root, {**env, **process.non_notification_environment(), 'NUMARATOR_API_KEY': ''},
                 'İlk yönetici oluşturulamadı.', failure=rejection,
                 payload=json.dumps({'username': credentials[0], 'password': credentials[1]}))
        process.check_cancelled()
        try:
            os.link(stage, database)
        except FileExistsError:
            raise LauncherError('Başka bir işlem veritabanını oluşturdu. Yeniden başlatın.') from None


def _migrate_existing_database(project, profile, database, settings, notify):
    from scripts.launcher.installation import backend_inspection

    media = (project.backend / settings['PRIVATE_MEDIA_ROOT']).resolve()
    inspection_env = {**settings, **process.non_notification_environment(), 'NUMARATOR_API_KEY': ''}

    def cancelled():
        process.check_cancelled()
        return False

    notify('phase', 'Veritabanı migration durumu denetleniyor.')
    run_backed_up_migrations(
        project, profile,
        lambda: backend_inspection(project, profile, configuration=inspection_env),
        lambda: _django(project, settings, ['migrate', '--noinput'], timeout=1800),
        lambda: _django(project, settings, ['migrate', '--check']),
        lambda message: notify('phase', message),
        storage=(database, media), cancelled=cancelled, timeout=1800,
    )


def _gates(project, values, settings, notify):
    for field, args in (
        ('deploy_check', ['check', '--deploy']), ('migration_check', ['migrate', '--check']),
        ('collectstatic', ['collectstatic', '--noinput']), ('verify_frontend', ['verify_frontend_artifact']),
    ):
        if values.get(field, False):
            notify('phase', ' '.join(args))
            _django(project, settings, args)


def _startup_diagnostic(project, web, local):
    """On child exit only, recover a missing import without exposing stderr."""
    from .profile_diagnostics import django_failure
    code = 'import django; django.setup()' if local else 'import uvicorn, django; django.setup()'
    try:
        probe = process.controlled_run([str(project.python), '-c', code], cwd=project.backend,
                env=process.environment(web), text=True, encoding='utf-8', errors='replace',
                capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    return django_failure('startup', probe.stderr, web)


def _ready(children, origin, certificate, frontend, heartbeats, diagnose):
    deadline = time.monotonic() + 90
    names = (['Django', 'Vite'] if frontend else ['HTTPS sunucusu']) + ['İş worker', 'Bildirim worker', 'Temizlik worker']
    pending = []
    while time.monotonic() < deadline:
        process.check_cancelled()
        for label, child in zip(names, children):
            if child.poll() is not None:
                remedy = ('Kaynaklar sekmesinde frontend bağımlılıklarını kontrol edin.' if label == 'Vite' else
                          diagnose() or 'Kaynaklar sekmesinde Python paketlerini ve seçili .env ayarlarını kontrol edin.')
                raise LauncherError(f'{label} başlangıç sırasında kapandı (kod {child.returncode}). {remedy}')
        pending = [label for name, label in zip(('job', 'notification', 'cleanup'), names[-3:])
                   if not worker_has_startup_marker(heartbeats, name)]
        if not probe_http(origin + '/health/live/', certificate):
            pending.append(names[0])
        if frontend and not probe_http(frontend + '/app/'):
            pending.append('Vite')
        if not pending:
            return
        time.sleep(0.25)
    raise LauncherError('Başlatma süresinde yanıt vermeyen bileşenler: ' + ', '.join(pending))


def _serve(project, values, connection, settings, notify):
    from .profile_resources import node_environment

    local = values['profile'] == 'dev'
    host, port = connection['host'], connection['backend_port']
    frontend_port = connection['frontend_port']
    reload = values.get('live_reload', True)
    browser_host = '127.0.0.1' if host == '0.0.0.0' else host
    frontend = runtime.public_url(host, frontend_port) if local else None
    certificate = None if local else connection['tls_cert_file']
    origin = runtime.public_url(host, port) if local else runtime.production_url(browser_host, port)
    web = {**settings, **process.non_notification_environment(), 'NUMARATOR_API_KEY': ''}
    node = node_environment() if local else {}
    vite = project.frontend / 'node_modules' / 'vite' / 'bin' / 'vite.js'
    if local and not vite.is_file():
        raise LauncherError('Vite giriş dosyası eksik. Kaynaklar sekmesinden frontend bağımlılıklarını kurun.')
    with tempfile.TemporaryDirectory(prefix='awcenter-workers-') as temp, process.server_console():
        heartbeats = Path(temp)
        with process.starting_processes() as children:
            if local:
                command = [project.python, project.manage_py, 'runserver', f'{host}:{port}']
                if not reload:
                    command.append('--noreload')
                children.append(process.start(command, project.backend, extra_env=web))
                with process.frontend_environment(True), process_environment(node):
                    children.append(process.start([node['AWCENTER_MANAGED_NODE'], vite, '--host', host,
                                                   '--port', str(frontend_port), '--strictPort'], project.frontend,
                            extra_env={'VITE_API_URL': origin, 'AWCENTER_VITE_RELOAD': '1' if reload else '0',
                                       'AWCENTER_MANAGED_PYTHON': str(project.python)}))
            else:
                children.append(runtime.start_production_backend(project, host, port, Path(certificate),
                                Path(connection['tls_key_file']), web))
            children.extend(start_job_workers(project, settings, include_doors_if_enabled=True,
                                               heartbeat_dir=heartbeats, protect_credentials=True,
                                               isolate_integrations=True))
            _ready(children, origin, certificate, frontend, heartbeats, lambda: _startup_diagnostic(project, web, local))
            notify('ready', (frontend or origin) + '/app/')
            process.supervise(children)


def _create_tls(project, connection):
    cert, key = (Path(connection[field]) for field in ('tls_cert_file', 'tls_key_file'))
    helper = Path(runtime.__file__).with_name('cert_pair.py')
    with process.frontend_environment(True):
        result = _command([project.python, '-I', helper, connection['host']], project.root, {},
                          'TLS sertifikası oluşturulamadı. Python bağımlılıklarını kontrol edin.')
    pem, private_key = json.loads(result.stdout)
    with installation_lock(profiles.installation_home()):
        for target in (cert, key):
            require_unlinked(target)
            if target.exists() and not target.is_file():
                raise LauncherError('TLS sertifikası ve özel anahtar için dosya yolları seçin.')
        if cert.resolve() == key.resolve() or (cert.exists() and key.exists() and cert.samefile(key)):
            raise LauncherError('Sertifika ve anahtar için iki farklı dosya yolu seçin.')
        for directory in {cert.parent, key.parent}:
            directory.mkdir(parents=True, exist_ok=True)
        _publish_tls_pair(cert, key, pem, private_key)
    return {'tls_cert_file': str(cert), 'tls_key_file': str(key)}


def _publish_tls_pair(cert, key, pem, private_key):
    # Stage beside each destination so replacement also works across volumes.
    with tempfile.TemporaryDirectory(dir=cert.parent) as cert_stage, tempfile.TemporaryDirectory(dir=key.parent) as key_stage:
        staged_cert, staged_key = Path(cert_stage) / 'server.crt', Path(key_stage) / 'server.key'
        profiles._write_new(staged_cert, pem)
        profiles._write_new(staged_key, private_key)
        previous_cert = Path(cert_stage) / 'previous.crt'
        if cert.exists():
            os.link(cert, previous_cert)
        os.replace(staged_cert, cert)
        try:
            os.replace(staged_key, key)
        except BaseException:
            if previous_cert.exists():
                os.replace(previous_cert, cert)
            else:
                cert.unlink()
            raise


def execute(action, values, notify, ask):
    from .profile_resources import node_environment, selected_project

    project = selected_project(values)
    selected = _selected(values)
    connection = _connection(values, selected)
    if action in ('tls', 'run') and not connection['host']:
        raise LauncherError('IPv4 alanına sunucunun adresini girin veya .env içinde IPV4_ADDRESS belirtin.')
    if (action == 'tls' or action == 'run' and values['profile'] == 'prod') and not all(
            connection[field] for field in ('tls_cert_file', 'tls_key_file')):
        raise LauncherError('TLS_CERT_FILE ve TLS_KEY_FILE için dosya yolları belirtin.')
    if not project.python.is_file():
        raise LauncherError('Proje Python ortamı bulunamadı. Kaynaklar sekmesinden bağımlılıkları kurun.')
    if action == 'tls':
        return _create_tls(project, connection)
    if action not in ('build', 'run'):
        raise LauncherError('Geçersiz profil işlemi.')
    settings, database, stored = _settings(project, values, connection, selected)
    if action == 'build':
        notify('phase', 'Frontend derleniyor.')
        with process.frontend_environment(True), process_environment(node_environment()):
            _command([*process.npm_command(), 'run', 'build'], project.frontend, {},
                     'Frontend derlemesi başarısız.', timeout=1800)
        _identity(project, profiles.installation_home(), database, settings, stored)
        notify('phase', 'Statik dosyalar yayınlanıyor.')
        _django(project, settings, ['collectstatic', '--noinput'])
        return
    if values['profile'] == 'prod':
        import ssl
        try:
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
                connection['tls_cert_file'], connection['tls_key_file'], password=lambda: '')
        except (OSError, ValueError):
            raise LauncherError('TLS dosyalarını seçin veya profil için bir sertifika oluşturun.') from None
    runtime.require_port(connection['host'], connection['backend_port'])
    if values['profile'] == 'dev':
        if connection['backend_port'] == connection['frontend_port']:
            raise LauncherError('Backend ve frontend portları farklı olmalıdır.')
        runtime.require_port(connection['host'], connection['frontend_port'])
    claim_storage(project, values['profile'], database, settings['PRIVATE_MEDIA_ROOT'])
    home = profiles.installation_home()
    _identity(project, home, database, settings, stored)
    migration_profile = {'name': values['profile'], 'installation_home': str(home),
                         'source_root': str(project.root)}
    if values.get('migrate_on_start') is True and database.is_file():
        if values.get('env_file'):
            migration_profile['env_file'] = str(Path(values['env_file']).expanduser().absolute())
        elif stored:
            migration_profile['env_file'] = str(home / 'config' / (values['profile'] + '.env'))
        _migrate_existing_database(project, migration_profile, database, settings, notify)
    else:
        if has_unresolved_migration(migration_profile):
            raise LauncherError('Önceki migration tamamlanamadı. Yedek ve migration durumunu kontrol edin.')
        _first_database(project, database, settings, ask, notify)
    if values['profile'] == 'prod':
        _gates(project, values, settings, notify)
    _serve(project, values, connection, settings, notify)
