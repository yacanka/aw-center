"""Bounded readiness checks for launcher-owned foreground processes."""

from __future__ import annotations

import ssl
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .model import LauncherError
from .process import check_cancelled


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def probe_http(url: str, certificate: str | None = None) -> bool:
    """Check only the exact local application origin, without proxy or redirect."""
    handlers = [ProxyHandler({}), _NoRedirect()]
    if certificate:
        handlers.append(HTTPSHandler(context=ssl.create_default_context(cafile=certificate)))
    try:
        with build_opener(*handlers).open(Request(url), timeout=1) as response:
            return response.status == 200
    except (OSError, HTTPError, URLError):
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
) -> None:
    """Require HTTP and this launch's worker identities before announcing readiness."""
    deadline = time.monotonic() + timeout
    while True:
        check_cancelled()
        if any(process.poll() is not None for process in processes):
            raise LauncherError("Başlatılan bir süreç kapandı; uygulama hazır değil.")
        production = profile["name"] == "prod"
        host, port = profile["host"], profile["backend_port"]
        origin = f"https://{host}:{port}" if production else f"http://{host}:{port}"
        path = "/health/ready/" if production else "/health/live/"
        http_ready = probe_http(origin + path, profile.get("tls_cert_file") if production else None)
        if not production:
            http_ready = probe_http(f"http://{host}:{profile['frontend_port']}/app/") and http_ready
        markers_ready = all((heartbeat_dir / name).is_file() for name in ("job", "notification", "cleanup"))
        if http_ready and markers_ready and worker_check():
            return
        if time.monotonic() >= deadline:
            raise LauncherError("Uygulama süre sınırında hazır olmadı; web ve worker kontrollerini inceleyin.")
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
