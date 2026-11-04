"""Real Windows acceptance helpers: OS egress denial and authenticated HTTP."""
from contextlib import contextmanager
import hashlib
from http.cookiejar import CookieJar
import io
import ipaddress
import json
from pathlib import Path
import secrets
import ssl
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, ProxyHandler, Request, build_opener
import uuid
import zipfile


@contextmanager
def deny_external_network(host):
    """Disposable CI host only; test application keeps its ordinary token.

    Rule names are random and only these rules are removed. Loopback and the
    application's own IPv4 remain reachable; all other IPv4/IPv6 is denied.
    Failure to install the OS rule fails acceptance, never silently skips it.
    """
    networks = [ipaddress.ip_network('0.0.0.0/0')]
    for exclusion in (ipaddress.ip_network('127.0.0.0/8'), ipaddress.ip_network(host + '/32')):
        networks = [part for network in networks for part in
                    (network.address_exclude(exclusion) if exclusion.subnet_of(network) else [network])]
    remote = ','.join(map(str, networks)) + ',::/0'
    names = []
    try:
        name = 'AWC-acceptance-' + uuid.uuid4().hex
        result = subprocess.run(['netsh', 'advfirewall', 'firewall', 'add', 'rule',
            'name=' + name, 'dir=out', 'action=block', 'enable=yes', 'profile=any',
            'remoteip=' + remote], capture_output=True, timeout=30)
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
