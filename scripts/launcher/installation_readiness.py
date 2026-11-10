"""Bounded readiness checks for launcher-owned foreground processes."""

from __future__ import annotations

import json
import ssl
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .model import LauncherError
from .local_tls import local_server_context
from .process import check_cancelled


class StartupReadinessError(LauncherError):
    code = 'startup_not_ready'
    remedy = ('Raporda beklenen bileşenleri kontrol edin. Hazırla ve Başlat ile yeniden deneyebilirsiniz; '
              'mevcut ortam ve veritabanı korunur.')



class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _http_failure(error: HTTPError) -> str:
    message = f'HTTP {error.code}'
    if error.code != 503:
        return message
    # Only the readiness contract's boolean fields may enter a safe report.
    try:
        payload = json.loads(error.read(4097))
        checks = payload.get('checks') if isinstance(payload, dict) else None
        if isinstance(checks, dict):
            failed = [label for key, label in (('database', 'veritabanı'), ('cache', 'önbellek'),
                                               ('frontend', 'frontend dosyaları')) if checks.get(key) is False]
            if failed:
                message += '; hazır olmayan: ' + ', '.join(failed)
    except (ValueError, OSError, RecursionError):
        pass  # An invalid/unfinished body must not hide the known HTTP status.
    return message


def _connection_failure(error) -> str:
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        code = getattr(reason, 'verify_code', None)
        return 'TLS sertifika doğrulaması başarısız' + (f' (kod {code})' if type(code) is int else '')
    if isinstance(reason, ssl.SSLError):
        return 'TLS bağlantısı kurulamadı'
    if isinstance(reason, TimeoutError):
        return 'bağlantı veya yanıt zaman aşımı (1 saniye)'
    if isinstance(reason, ConnectionRefusedError):
        return 'bağlantı reddedildi'
    return 'bağlantı kurulamadı'


def probe_http(url: str, certificate: str | None = None, *, diagnostic=None) -> bool:
    """Check only the exact local application origin, without proxy or redirect."""
    handlers = [ProxyHandler({}), _NoRedirect()]
    if certificate:
        handlers.append(HTTPSHandler(context=local_server_context(certificate)))
    try:
        with build_opener(*handlers).open(Request(url), timeout=1) as response:
            if response.status == 200:
                return True
            message = f'HTTP {int(response.status)}'
    except HTTPError as error:
        try:
            message = _http_failure(error)
        finally:
            error.close()
    except (OSError, URLError) as error:
        message = _connection_failure(error)
    if diagnostic is not None:
        diagnostic(message)
    return False


def healthy(profile: dict, worker_check: Callable[[], bool]) -> bool:
    production = profile['name'] == 'prod'
    host, port = profile['host'], profile['backend_port']
    origin = f'https://{host}:{port}' if production else f'http://{host}:{port}'
    path = '/health/ready/' if production else '/health/live/'
    ready = probe_http(origin + path, profile.get('tls_cert_file') if production else None)
    if not production:
        ready = probe_http(f"http://{host}:{profile['frontend_port']}/app/") and ready
    return worker_check() and ready


class HealthMonitor:
    """Bounded checks on the supervisor thread; transitions never restart servers."""
    def __init__(self, check, emit, *, clock=time.monotonic):
        self.check, self.emit, self.clock = check, emit, clock
        self.next_check = clock() + 10
        self.healthy = True
        self.failures = self.successes = 0

    def __call__(self):
        if self.clock() < self.next_check:
            return
        check_cancelled()
        result = self.check()
        self.successes = self.successes + 1 if result else 0
        self.failures = 0 if result else self.failures + 1
        if self.failures >= 3:
            self.healthy = False
        elif self.successes >= 2:
            self.healthy = True
        self.emit({'type': 'health', 'healthy': self.healthy, 'check_ok': result,
                   'message': ('Web ve worker sağlıklı.' if self.healthy and result else
                               f'Sağlık kontrolü başarısız ({self.failures}/3); yeniden denetlenecek.' if self.healthy else
                               'Web veya worker sağlık kontrolü başarısız; iyileşme izleniyor.')})
        self.next_check = self.clock() + 10


def wait_until_ready(
    processes: list,
    profile: dict,
    heartbeat_dir: Path,
    *,
    worker_check: Callable[[], bool] = lambda: False,
    timeout: float = 60,
    progress=None,
) -> None:
    """Require HTTP and this launch's worker identities before announcing readiness."""
    deadline = time.monotonic() + timeout
    previous = None
    while True:
        check_cancelled()
        for index, process in enumerate(processes):
            code = process.poll()
            if code is not None:
                raise StartupReadinessError(f'Başlatılan süreç {index + 1} kapandı (çıkış kodu: {int(code)}); uygulama hazır değil.')
        production = profile["name"] == "prod"
        host, port = profile["host"], profile["backend_port"]
        origin = f"https://{host}:{port}" if production else f"http://{host}:{port}"
        path = "/health/ready/" if production else "/health/live/"
        pending = []
        details = []
        if not probe_http(origin + path, profile.get('tls_cert_file') if production else None,
                          diagnostic=details.append):
            label = 'backend HTTPS' if production else 'backend HTTP'
            pending.append(label + (': ' + details[-1] if details else ''))
        if not production and not probe_http(f"http://{host}:{profile['frontend_port']}/app/"):
            pending.append('frontend HTTP')
        for name, label in (('job', 'iş worker kimliği'), ('notification', 'bildirim worker'),
                            ('cleanup', 'temizlik worker')):
            if not (heartbeat_dir / name).is_file():
                pending.append(label)
        if not worker_check():
            pending.append('worker heartbeat')
        if not pending:
            return
        message = 'Hazır olması bekleniyor: ' + ', '.join(pending)
        if progress is not None and message != previous:
            progress(message)
            previous = message
        if time.monotonic() >= deadline:
            raise StartupReadinessError('Başlatma süresinde hazır olmayan bileşenler: ' + ', '.join(pending) + '.')
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
