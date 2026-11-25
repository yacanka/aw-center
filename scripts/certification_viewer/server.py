"""Loopback-only delivery of the bundled UI and the selected Certification data."""

from datetime import date
from http import HTTPStatus
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import sqlite3
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from .source import SourceError


class ViewerServer(ThreadingHTTPServer):
    def __init__(self, source, assets):
        super().__init__(('127.0.0.1', 0), ViewerHandler)
        self.source = source
        self.assets = assets
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.ui_path = f'/ui/{secrets.token_hex(8)}/'
        self.cookie = secrets.token_urlsafe(32)
        self.session = secrets.token_urlsafe(32)
        self._ticket = ''
        self._expiry = 0
        self._lock = Lock()

    def new_ticket(self):
        with self._lock:
            self._ticket = secrets.token_urlsafe(32)
            self._expiry = monotonic() + 60
            return self._ticket

    def redeem(self, candidate):
        with self._lock:
            if not self._ticket or monotonic() > self._expiry or not _matches(candidate, self._ticket):
                return False
            self._ticket = ''
            return True


def _matches(received, expected):
    return secrets.compare_digest(received.encode('utf-8'), expected.encode('ascii'))


def _json_default(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError('Unsupported JSON data')


class ViewerHandler(BaseHTTPRequestHandler):
    timeout = 5
    server_version = 'CertificationDashboard'

    def log_message(self, *args):
        # Requests may contain local identifiers. The native window reports user-facing errors.
        pass

    def reply(self, status, body=b'', mime='text/plain; charset=utf-8', headers=()):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def data(self, value, status=200):
        self.reply(status, json.dumps(value, default=_json_default, ensure_ascii=False).encode(), 'application/json')

    def allowed_host(self):
        return self.headers.get('Host') == self.server.origin.removeprefix('http://')

    def authorized(self):
        origin = self.headers.get('Origin')
        return (self.allowed_host() and origin in (None, self.server.origin)
                and _matches(self.headers.get('X-Dashboard-Session', ''), self.server.session))

    def do_POST(self):
        if not self.allowed_host():
            return self.reply(403)
        if self.path == '/open':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 256:
                    return self.reply(400)
                ticket = parse_qs(self.rfile.read(length).decode('ascii')).get('ticket', [''])[0]
            except (ValueError, UnicodeError):
                return self.reply(400)
            if not self.server.redeem(ticket):
                return self.reply(403)
            cookie = f'viewer={self.server.cookie}; Path={self.server.ui_path}; HttpOnly; SameSite=Lax'
            return self.reply(303, headers=[('Set-Cookie', cookie), ('Location', self.server.ui_path)])
        if not self.authorized():
            return self.reply(403)
        if self.path != '/viewer/refresh':
            return self.reply(404)
        try:
            self.data(self.server.source.refresh())
        except SourceError as exc:
            self.data({'detail': str(exc)}, 409)

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403)
        path = urlsplit(self.path).path
        if path == self.server.ui_path:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get('Cookie', ''))
            except CookieError:
                return self.reply(403)
            cookie = cookies.get('viewer')
            if cookie is None or not _matches(cookie.value, self.server.cookie):
                return self.reply(403)
            page = (self.server.assets / 'index.html').read_bytes()
            return self.reply(200, page.replace(b'__DASHBOARD_SESSION__', self.server.session.encode()), 'text/html; charset=utf-8')
        if re.fullmatch(r'/assets/[A-Za-z0-9_.$-]+', path):
            asset = self.server.assets / path.lstrip('/')
            if asset.is_file():
                mime = {'.js': 'text/javascript', '.css': 'text/css'}.get(asset.suffix, 'application/octet-stream')
                return self.reply(200, asset.read_bytes(), mime)
        if not path.startswith('/viewer/'):
            return self.reply(404)
        if not self.authorized():
            return self.reply(403)
        if path == '/viewer/projects':
            return self.data(self.server.source.status())
        match = re.fullmatch(r'/viewer/projects/([-\w]+)/(dashboard|documents)', path)
        if not match:
            return self.reply(404)
        try:
            self.data(self.server.source.read(match[2], match[1]))
        except LookupError:
            self.reply(HTTPStatus.NOT_FOUND)
        except (OSError, ValueError, sqlite3.Error):
            self.data({'detail': 'Veri okunamadı. Kaynağı yenileyin veya farklı bir dosya seçin.'}, 409)
