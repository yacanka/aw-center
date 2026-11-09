"""Real Windows acceptance helpers: OS egress denial and authenticated HTTP."""
from contextlib import contextmanager
import hashlib
from http.cookiejar import CookieJar
import io
import ipaddress
import json
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, ProxyHandler, Request, build_opener
import uuid
import zipfile


class StartupEvidence:
    """Keep bounded facts from worker IPC and the desktop browser boundary."""

    _phases = {
        'ön kontrol': 'preflight', 'runtime hazırlığı': 'runtime', 'kilitli bağımlılıklar': 'dependencies',
        'TLS sertifika ve IP doğrulaması': 'tls', 'özel profil': 'profile', 'veritabanı şeması': 'schema',
        'ilk yönetici': 'admin', 'ek araçlar ve varlıklar': 'features',
        'production build ve deployment kontrolleri': 'build_and_checks',
        'Uygulama ve worker süreçleri başlatılıyor': 'startup',
    }

    def __init__(self):
        self.begin()
        self.ready_url = None
        self.ready_count = self.prompts = self.browser_calls = 0
        self.browser_order_ok = True
        self.browser_ms = None
        self.locked_branches = []
        self.source_attempts = dict.fromkeys(('python_packages', 'npm_packages', 'runtime'), 0)
        self.failed = False

    def begin(self, now=None):
        self.started = self.phase_started = time.monotonic() if now is None else now
        self.phase = 'planning'
        self.phase_ms = {}

    def _finish_phase(self, now):
        if self.phase is not None:
            elapsed = round(1000 * (now - self.phase_started))
            self.phase_ms[self.phase] = self.phase_ms.get(self.phase, 0) + elapsed
            self.phase = None

    def observe(self, event, *, now=None):
        now = time.monotonic() if now is None else now
        kind = event.get('type')
        if kind == 'resources' and event.get('action') in {'start', 'provision'}:
            self.locked_branches.append(event['action'])
        elif kind == 'phase':
            phase = self._phases.get(event.get('message'))
            if self.phase and phase:
                self._finish_phase(now)
                self.phase, self.phase_started = phase, now
            attempt = re.fullmatch(r'(Python paketleri|npm paketleri|node|python|npm): izinli kaynak [0-9]+/[0-9]+ deneniyor',
                                   event.get('message', ''))
            if attempt:
                group = {'Python paketleri': 'python_packages', 'npm paketleri': 'npm_packages'}
                self.source_attempts[group.get(attempt[1], 'runtime')] += 1
        elif kind == 'input':
            self.prompts += 1
        elif kind == 'ready':
            self._finish_phase(now)
            self.ready_url = event.get('url')
            self.ready_count += 1
        elif kind == 'error' or (kind == 'done' and not event.get('ok')):
            self.failed = True
        if kind == 'done':
            self._finish_phase(now)

    def open_browser(self, url):
        self.browser_calls += 1
        self.browser_order_ok &= bool(self.ready_url and url == self.ready_url)
        self.browser_ms = round(1000 * (time.monotonic() - self.started))
        return True

    def summary(self):
        return dict(locked_branches=self.locked_branches, source_attempts=self.source_attempts, phase_ms=self.phase_ms,
                    prompts=self.prompts, ready_events=self.ready_count, browser_calls=self.browser_calls,
                    browser_after_ready=self.browser_order_ok, click_to_browser_ms=self.browser_ms)

    def check(self, *, warm):
        assert not self.failed, 'The lifecycle returned an error'
        assert self.ready_count == self.browser_calls == 1 and self.browser_order_ok, self.summary()
        assert self.locked_branches == (['start'] if warm else ['provision']), self.summary()
        assert self.prompts == (0 if warm else 1), self.summary()
        if warm:
            assert not any(self.source_attempts.values()), self.summary()


@contextmanager
def deny_external_network(host, programs):
    """Disposable CI host only; test application keeps its ordinary token.

    Rule names are random and only these rules are removed. Loopback and the
    application's own IPv4 remain reachable; all other IPv4/IPv6 is denied
    for the explicit application interpreters and executables. The CI runner
    must retain its separate control-plane connection.
    Failure to install the OS rule fails acceptance, never silently skips it.
    """
    programs = tuple(dict.fromkeys(str(Path(program).resolve()) for program in programs))
    if not programs:
        raise ValueError('Explicit application programs are required for network containment')
    networks = [ipaddress.ip_network('0.0.0.0/0')]
    for exclusion in (ipaddress.ip_network('127.0.0.0/8'), ipaddress.ip_network(host + '/32')):
        networks = [part for network in networks for part in
                    (network.address_exclude(exclusion) if exclusion.subnet_of(network) else [network])]
    # netsh rejects a /0 prefix; two /1 networks cover the IPv6 space.
    remote = ','.join(map(str, networks)) + ',::/1,8000::/1'
    names = []
    try:
        for program in programs:
            name = 'AWC-acceptance-' + uuid.uuid4().hex
            result = subprocess.run(['netsh', 'advfirewall', 'firewall', 'add', 'rule',
                'name=' + name, 'dir=out', 'action=block', 'enable=yes', 'profile=any',
                'program=' + program, 'remoteip=' + remote], capture_output=True, timeout=30)
            if result.returncode:
                raise AssertionError('Windows Firewall rule creation failed: ' +
                                     result.stdout.decode(errors='replace')[:2000] +
                                     result.stderr.decode(errors='replace')[:2000])
            names.append(name)
        yield
    finally:
        for name in names:
            subprocess.run(['netsh', 'advfirewall', 'firewall', 'delete', 'rule', 'name=' + name],
                           capture_output=True, timeout=30, check=True)


def acceptance_programs(executable, directory, source, python, node):
    """Cover system/managed tools and future dev/prod venv paths before setup.

    pip runs through Python and npm through Node. No installer needs a separate
    downloader process. Paths are derived from the same pinned catalog and
    source fingerprint as installation, including files not created yet.
    """
    from scripts.launcher.installation_sources import load_catalog
    from scripts.launcher.toolchain import _directory
    from scripts.manager.payload import production_source_path, verify_source_payload
    home = directory / 'local/AWCenter'
    catalog = load_catalog()
    roots = [source]
    programs = [python, node]
    if executable is not None:
        programs.append(executable)
        fingerprint = verify_source_payload(source)['fingerprint']
        roots.extend((production_source_path(home, fingerprint), home / 'releases' / fingerprint / 'source'))
    programs.extend(_directory(home, catalog[name]) / catalog[name].executable
                    for name in ('python', 'node'))
    for root in roots:
        programs.extend(root / '.venv/Scripts' / name for name in
                        ('python.exe', 'pythonw.exe', 'pip.exe', 'pip3.exe', 'pip3.11.exe'))
    return programs


def docx_bytes(text):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>')
    return data.getvalue()


class LiveAcceptance:
    def __init__(self, origin, certificate=None, frontend_origin=None):
        self.origin = origin
        self.frontend_origin = frontend_origin or origin
        self.cookies = CookieJar()
        self.handlers = [ProxyHandler({})]
        if certificate:
            self.handlers.append(HTTPSHandler(context=ssl.create_default_context(cafile=str(certificate))))
        self.client = build_opener(*self.handlers, HTTPCookieProcessor(self.cookies))

    def request(self, path, *, data=None, headers=None, csrf=True, anonymous=False):
        headers = {'Referer': self.origin + '/app/', **(headers or {})}
        if csrf:
            token = next((cookie.value for cookie in self.cookies if cookie.name == 'csrftoken'), None)
            if token:
                headers['X-CSRFToken'] = token
        client = build_opener(*self.handlers) if anonymous else self.client
        return client.open(Request(self.origin + path, data=data, headers=headers), timeout=30)

    def json(self, path, **kwargs):
        with self.request(path, **kwargs) as response:
            return json.load(response)

    def exercise(self, password):
        assert self.json('/api/session/')['state'] == 'anonymous'
        credentials = json.dumps({'username': 'U12345', 'password': password}).encode()
        try:
            self.request('/api/session/', data=credentials, headers={'Content-Type': 'application/json'}, csrf=False)
        except HTTPError as error:
            assert error.code == 403
            error.close()
        else:
            raise AssertionError('Login accepted an unsafe request without CSRF')
        session = self.json('/api/session/', data=credentials, headers={'Content-Type': 'application/json'})
        assert session['state'] == 'authenticated'
        assert self.json('/api/session/')['user']['username'] == 'U12345'
        with self.client.open(self.frontend_origin + '/app/', timeout=30) as response:
            assert b'<html' in response.read().lower()
        boundary = 'awc' + secrets.token_hex(16)
        body = bytearray()
        for name, text in (('first', 'First revision.'), ('second', 'Second revision.')):
            body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.docx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n').encode())
            body.extend(docx_bytes(text))
            body.extend(b'\r\n')
        body.extend(f'--{boundary}--\r\n'.encode())
        job = self.json('/api/tools/compare/jobs/', data=bytes(body), headers={
            'Content-Type': 'multipart/form-data; boundary=' + boundary, 'Idempotency-Key': uuid.uuid4().hex})
        deadline = time.monotonic() + 120
        while job['status'] not in {'succeeded', 'failed', 'cancelled'} and time.monotonic() < deadline:
            time.sleep(0.25)
            job = self.json('/api/jobs/' + job['id'] + '/')
        assert job['status'] == 'succeeded', 'Real worker did not complete the DOCX comparison'
        path = job['download_url']
        with self.request(path) as response:
            output = response.read()
            assert output.startswith(b'PK'), 'Comparison report is not a DOCX archive'
        try:
            self.request(path, anonymous=True, csrf=False)
        except HTTPError as error:
            assert error.code in (401, 403, 404)
            error.close()
        else:
            raise AssertionError('Private job output was accessible without a session')
        return job['id'], hashlib.sha256(output).hexdigest()
