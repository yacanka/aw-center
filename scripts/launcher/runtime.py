"""Development, production, check, and test workflows."""

from __future__ import annotations

import os
import shlex
import socket
import subprocess
from pathlib import Path

from .dependencies import ensure_virtual_environment
from .discovery import infer_wsgi_application
from .job_worker import start_job_workers
from .model import LauncherError, Project, Scope
from .process import required_tool, start, supervise
from .quality import django, run_first_script, run_script, select_script


def check(project: Project, scope: Scope) -> None:
    """Run read-only backend and frontend quality checks."""
    scope.require_any()
    if scope.backend:
        ensure_virtual_environment(project, create=False)
        django(project, ["check"])
        django(project, ["makemigrations", "--check", "--dry-run"])
        django(project, ["migrate", "--check"])
    if scope.frontend:
        for candidates in (("format:check",), ("typecheck", "type-check")):
            run_first_script(project, candidates)
    print("[ok] checks completed")


def test(project: Project, scope: Scope) -> None:
    """Run repository-owned backend and frontend test commands."""
    scope.require_any()
    if scope.backend:
        ensure_virtual_environment(project, create=False)
        django(project, ["test"])
    if scope.frontend:
        run_first_script(project, ("test:ci", "test", "unit"))
    print("[ok] tests completed")


def dev(
    project: Project,
    scope: Scope,
    *,
    host: str,
    backend_port: int,
    frontend_port: int,
    no_backend_reload: bool,
    migrate: bool,
) -> None:
    """Run Django and Vite as launcher-owned foreground children."""
    scope.require_any()
    require_runtime_ports(scope, host, backend_port, frontend_port)
    processes = []
    if scope.backend:
        processes.append(start_backend(project, host, backend_port, frontend_port, no_backend_reload, migrate))
        processes.extend(start_job_workers(project, runtime_env(host, backend_port, frontend_port)))
    if scope.frontend:
        processes.append(start_frontend(project, host, backend_port, frontend_port))
    print_urls(scope, host, backend_port, frontend_port)
    supervise(processes)


def start_backend(
    project: Project, host: str, port: int, frontend_port: int, no_reload: bool, migrate: bool
) -> subprocess.Popen:
    """Prepare and start the Django development child."""
    ensure_virtual_environment(project, create=False)
    extra_env = runtime_env(host, port, frontend_port)
    if migrate:
        django(project, ["migrate", "--noinput"], extra_env)
    command = [project.python, "manage.py", "runserver", f"{host}:{port}"]
    if no_reload:
        command.append("--noreload")
    return start(command, project.backend, extra_env=extra_env)


def start_frontend(
    project: Project, host: str, backend_port: int, port: int
) -> subprocess.Popen:
    """Start the Vue development child with an ephemeral API URL."""
    script = select_script(project, ("dev", "serve", "start"), required=True)
    command = [required_tool("npm"), "run", script, "--", "--host", host, "--port", str(port)]
    if script == "dev":
        command.append("--strictPort")
    return start(command, project.frontend, extra_env=frontend_env(public_url(host, backend_port)))


def prod(
    project: Project,
    *,
    host: str,
    port: int,
    migrate: bool,
    build: bool,
    collect_static: bool,
    checks: bool,
    production_command: str | None,
) -> None:
    """Build, validate, and run one production WSGI process."""
    require_port(host, port)
    ensure_virtual_environment(project, create=False)
    extra_env = runtime_env(host, port, None)
    prepare_production(project, extra_env, migrate, build, collect_static, checks)
    command = production_argv(project, host, port, production_command)
    print(f"Production endpoint: {public_url(host, port)}")
    supervise([start(command, project.backend, extra_env=extra_env), *start_job_workers(project, extra_env)])


def prepare_production(
    project: Project,
    extra_env: dict[str, str],
    migrate: bool,
    build: bool,
    collect_static: bool,
    checks: bool,
) -> None:
    """Run the explicit pre-start production gates."""
    if build:
        run_script(project, "build")
    if checks:
        django(project, ["check", "--deploy", "--fail-level", "WARNING"], extra_env)
        django(project, ["migrate", "--check"], extra_env)
    if migrate:
        django(project, ["migrate", "--noinput"], extra_env)
    if collect_static:
        django(project, ["collectstatic", "--noinput"], extra_env)


def production_argv(project: Project, host: str, port: int, configured: str | None) -> list[str]:
    """Resolve an explicit server command or infer a Gunicorn command."""
    wsgi = infer_wsgi_application(project)
    if configured:
        values = {"host": host, "port": str(port), "wsgi": wsgi, "python": str(project.python)}
        try:
            return [part.format_map(values) for part in shlex.split(configured)]
        except KeyError as error:
            raise LauncherError(f"unknown production command placeholder: {error}") from error
    if os.name == "nt":
        cheroot = project.backend / "run_cheroot.py"
        if cheroot.is_file():
            return [str(project.python), cheroot.name]
        raise LauncherError("Windows production requires --production-command")
    return [str(project.python), "-m", "gunicorn", wsgi, "--bind", f"{host}:{port}"]


def runtime_env(host: str, backend_port: int, frontend_port: int | None) -> dict[str, str]:
    """Return ephemeral runtime overrides without reading or writing env files."""
    values = {"IPV4_ADDRESS": host, "PORT": str(backend_port)}
    if frontend_port is not None:
        values["DEV_FRONTEND_PORT"] = str(frontend_port)
        values["DEV_BACKEND_PORT"] = str(backend_port)
    return values


def frontend_env(backend_url: str) -> dict[str, str]:
    """Expose the backend URL only to the Vite child process."""
    return {"VITE_API_URL": backend_url}


def require_port(host: str, port: int | None) -> None:
    """Reject invalid or occupied ports instead of silently changing them."""
    if port is None:
        return
    if not 1 <= port <= 65535:
        raise LauncherError(f"invalid port: {port}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as error:
            raise LauncherError(f"port is unavailable: {host}:{port}") from error


def require_runtime_ports(scope: Scope, host: str, backend_port: int, frontend_port: int) -> None:
    """Validate only the ports used by the selected development scope."""
    require_port(host, backend_port if scope.backend else None)
    require_port(host, frontend_port if scope.frontend else None)


def public_url(host: str, port: int) -> str:
    """Return an HTTP URL with a browser-safe wildcard host."""
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}"


def print_urls(scope: Scope, host: str, backend_port: int, frontend_port: int) -> None:
    """Print the explicit endpoints selected for development."""
    if scope.backend:
        print(f"Backend:  {public_url(host, backend_port)}")
    if scope.frontend:
        print(f"Frontend: {public_url(host, frontend_port)}")
    print("Press Ctrl+C to stop.")
