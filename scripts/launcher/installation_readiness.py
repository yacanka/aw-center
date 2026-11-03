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
