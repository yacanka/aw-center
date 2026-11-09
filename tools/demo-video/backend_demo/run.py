"""Isolated AW Center recording server. Invoke with AW_VIDEO_DEMO=1 only."""
import argparse
import json
import os
import secrets
import signal
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STATE = REPO / '.runtime' / 'aw-center-video' / 'backend'
DIST = REPO / 'artifacts' / 'aw-center-video' / '.work' / 'dist'
PORT = 18765


def private_json(path, content):
    stage = path.with_suffix('.new')
    with stage.open('w', encoding='utf-8') as handle:
        os.chmod(stage, 0o600)
        json.dump(content, handle, ensure_ascii=False, indent=2)
    stage.replace(path)


def deny_connections(event, args):
    # A local listener accepts browser requests. Neither app nor worker needs an
    # outbound connection, including to other services on the local machine.
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname'}:
        raise PermissionError('The recording backend disables outbound network access.')


def prepare(reset):
    if os.environ.get('AW_VIDEO_DEMO') != '1':
        raise SystemExit('Explicit AW_VIDEO_DEMO=1 required.')
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if STATE.resolve() != STATE:
        raise SystemExit('Demo state must be a private local directory.')
    access_path = STATE / 'access.json'
    if not access_path.exists():
        private_json(access_path, {'admin': 'D10001', 'viewer': 'D10002', 'editor': 'D10003', 'password': secrets.token_urlsafe(24)})
    active = STATE / 'active.json'
    if reset:
        generation = Path(tempfile.mkdtemp(dir=STATE, prefix='state-'))
        config = Path(tempfile.mkdtemp(prefix='aw-center-video-policy-')).resolve()
        from cryptography.fernet import Fernet
        private_json(generation / 'keys.json', {'secret': secrets.token_urlsafe(50), 'jira': Fernet.generate_key().decode(), 'policy': str(config)})
    elif active.exists():
        generation = STATE / json.loads(active.read_text())['generation']
    else:
        raise SystemExit('Run the demo reset first.')
    if generation.parent != STATE or generation.resolve() != generation or not generation.name.startswith('state-'):
        raise SystemExit('Invalid demo state generation.')
    keys = json.loads((generation / 'keys.json').read_text())
    pptx_python = os.environ.get('AW_VIDEO_PPTX_PYTHON')
    if not pptx_python:
        selected = STATE.parent / 'author-python'
        pptx_python = selected.read_text(encoding='utf-8').strip() if selected.is_file() else sys.executable
    safe_env = {name: os.environ[name] for name in ('PATH', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'WINDIR') if name in os.environ}
    os.environ.clear()
    os.environ.update(safe_env)
    for name in ['private', 'media', 'cache', 'static', 'assets', 'tmp', 'home']:
        (generation / name).mkdir(exist_ok=True)
    profile = generation / 'profile.env'
    profile.touch()
    config = Path(keys['policy'])
    os.environ.update({
        'AW_VIDEO_PPTX_PYTHON': pptx_python, 'HOME': str(generation / 'home'), 'TMPDIR': str(generation / 'tmp'), 'AW_VIDEO_DEMO': '1',
        'DJANGO_SETTINGS_MODULE': 'awcenter.settings', 'AWCENTER_ENV_FILE': str(profile),
        'DEBUG': 'true', 'ALLOW_ALL_DEBUG_HOSTS': 'false', 'ALLOWED_HOSTS': '127.0.0.1,localhost,testserver',
        'SECRET_KEY': keys['secret'], 'DATABASE_URL': f"sqlite:///{generation / 'demo.sqlite3'}", 'DATABASE_CONN_MAX_AGE': '0',
        'PRIVATE_MEDIA_ROOT': str(generation / 'private'), 'MEDIA_ROOT': str(generation / 'media'),
        'STATIC_ROOT': str(generation / 'static'), 'CACHE_DIRECTORY': str(generation / 'cache'),
        'MODEL_RUNTIME_DIR': str(generation / 'assets'), 'CUSTOM_TEMPLATE_DIR': str(generation / 'assets'),
        'FRONTEND_DIST_DIR': str(DIST), 'DEV_FRONTEND_PORT': str(PORT), 'PORT': str(PORT),
        'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend', 'AWCENTER_MAIL_TRANSPORT': 'disabled',
        'FRONTEND_INVITATION_URL': f'http://127.0.0.1:{PORT}/app/invite', 'FRONTEND_RESET_URL': f'http://127.0.0.1:{PORT}/app/login',
        'JIRA_ENABLED': 'true', 'JIRA_URL': 'https://jira.example.invalid', 'JIRA_DEFAULT_PROJECT_KEY': 'DEMO',
        'JIRA_SESSION_ENCRYPTION_KEY': keys['jira'], 'DOORS_ENABLED': 'true', 'DOORS_DATABASE': 'Atlas Demo',
        'TEAMCENTER_ENABLED': 'true', 'TEAMCENTER_BASE_URL': 'https://teamcenter.example.invalid',
        'DOCPROOF_ENABLED': 'true', 'DOCPROOF_URL': 'https://docproof.example.invalid',
        'PROJECT_CONFIGURATION_FILE': str(config / 'projects.json'), 'DDF_ASSESSMENT_POLICY_FILE': str(config / 'ddf.json'),
        'GOKBEY_DCC_POLICY_FILE': str(config / 'dcc.json'), 'AW_DEMO_GENERATION': str(generation),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
    })
    tempfile.tempdir = str(generation / 'tmp')
    sys.path.insert(0, str(REPO / 'backend'))
    sys.addaudithook(deny_connections)
    import django
    django.setup()
    from projects.registry import get_project_definitions_by_capability
    if reset:
        projects = {p.slug: {'jira_component': 'Atlas Demo' if p.slug == 'gokbey' else f'Demo {p.slug}', 'aliases': [], 'dcc_label': 'Atlas', 'dcc_template_name': 'Atlas-DCC.docx', 'mail_template_name': 'atlas'} for p in get_project_definitions_by_capability('jira')}
        private_json(config / 'projects.json', {'schema_version': 1, 'projects': projects, 'cover_pages': {'match_text': 'ATL', 'match_label': 'Atlas Demo Projesi', 'default_label': 'Demo Projesi'}})
        private_json(config / 'ddf.json', {'schema_version': 1, 'prompt_prefix': 'Örnek yorum sınıflandırması.\n'})
    return generation


def adapters():
    import importlib.util
    for name in ['local_adapters', 'jira_demo', 'number_demo']:
        if importlib.util.find_spec(name):
            __import__(name).install()


def reset(state=STATE):
    from django.core.management import call_command
    from seed import seed
    call_command('migrate', interactive=False, verbosity=0)
    seed(state)


def clear_login_limits():
    from django.core.cache import cache
    from django.test import RequestFactory
    from users.throttles import LoginAccountThrottle, LoginAddressThrottle
    accounts = json.loads((STATE/'access.json').read_text())
    for role in ('admin','editor','viewer'):
        request = RequestFactory().post('/api/session/', {'username': accounts[role]}, REMOTE_ADDR='127.0.0.1')
        for throttle in (LoginAccountThrottle(), LoginAddressThrottle()):
            cache.delete(throttle.get_cache_key(request,None))


def serve():
    from django.core.handlers.wsgi import WSGIHandler
    from django.core.servers.basehttp import ThreadedWSGIServer, WSGIRequestHandler
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from worker import work
    if not (DIST / 'index.html').is_file():
        raise SystemExit('Build the recording frontend into artifacts/aw-center-video/.work/dist first.')
    clear_login_limits()
    stop = threading.Event()
    class LocalServer(ThreadedWSGIServer):
        def server_bind(self):
            # WSGIServer's portable default resolves its own FQDN via DNS.
            from socketserver import TCPServer
            TCPServer.server_bind(self)
            self.server_name, self.server_port = self.server_address
            self.setup_environ()
    with LocalServer(('127.0.0.1', PORT), WSGIRequestHandler) as server:
        server.set_app(StaticFilesHandler(WSGIHandler()))
        server.timeout = .3
        thread = threading.Thread(target=work, args=(stop,), name='demo-worker')
        thread.start()
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, lambda *_: stop.set())
        try:
            print(f'Demo ready on http://127.0.0.1:{PORT}/app/', flush=True)
            while not stop.is_set():
                server.handle_request()
        finally:
            stop.set()
            thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['reset', 'serve', 'check', 'refresh-fixtures', 'clear-login-limits'])
    command = parser.parse_args().command
    generation = prepare(command in {'reset','check'})
    adapters()
    if command == 'reset':
        reset()
        private_json(STATE / 'active.json', {'generation': generation.name})
    elif command == 'clear-login-limits':
        clear_login_limits()
    elif command == 'serve':
        serve()
    elif command == 'refresh-fixtures':
        from examples import write_examples
        write_examples(STATE / 'examples')
    else:
        from verify import verify
        import shutil
        shutil.copyfile(STATE / 'access.json', generation / 'access.json')
        reset(generation)
        verify(generation, generation)

if __name__ == '__main__':
    main()
