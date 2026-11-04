"""Local development, check, and test workflows."""

from __future__ import annotations

import ipaddress
import os
import socket
import subprocess
import sys
from pathlib import Path
from collections.abc import Callable

from .dependencies import ensure_virtual_environment
from .job_worker import start_job_workers
from .model import LauncherError, Project, Scope
from .process import (frontend_environment, non_notification_environment, npm_command,
                      required_tool, run, start, starting_processes, supervise)
from .quality import django, run_first_script, run_script, select_script


def check(project: Project, scope: Scope) -> None:
    """Run read-only backend and frontend quality checks."""
    scope.require_any()
    if scope.backend:
        ensure_virtual_environment(project, create=False)
        django(project, ["check"])
        isolated_database = {"DATABASE_URL": "sqlite:///:memory:"}
        django(
            project,
            ["makemigrations", "--check", "--dry-run"],
            isolated_database,
        )
        django(project, ["migrate", "--plan"], isolated_database)
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
        run(
            [
                project.python,
                "-m",
                "unittest",
                "scripts.test_launcher",
                "scripts.test_launcher_jobs",
                "scripts.test_release_metadata",
            ],
            project.root,
        )
    if scope.frontend:
        run_first_script(project, ("test:ci", "test", "unit"))
    print("[ok] tests completed")


from .resource_locks import windows_lifecycle


@windows_lifecycle('dev')
def dev(
    project: Project,
    scope: Scope,
    *,
    host: str,
    backend_port: int,
    frontend_port: int,
    no_backend_reload: bool,
    migrate: bool,
    exclude_doors: bool = False,
    ready: Callable[[list[subprocess.Popen]], None] | None = None,
    worker_heartbeat_dir: Path | None = None,
    protect_credentials: bool = False,
    health=None,
) -> None:
    """Run Django and Vite as launcher-owned foreground children."""
    scope.require_any()
    require_runtime_ports(scope, host, backend_port, frontend_port)
    with starting_processes() as processes:
        if scope.backend:
            processes.append(
                start_backend(
                    project,
                    host,
                    backend_port,
                    frontend_port,
                    no_backend_reload,
                    migrate,
                    **({"protect_credentials": True} if protect_credentials else {}),
                )
            )
            processes.extend(
                start_job_workers(
                    project,
                    runtime_env(host, backend_port, frontend_port),
                    include_doors_if_enabled=not exclude_doors,
                    **({"heartbeat_dir": worker_heartbeat_dir} if worker_heartbeat_dir else {}),
                    **({"protect_credentials": True} if protect_credentials else {}),
                )
            )
        if scope.frontend:
            processes.append(start_frontend(project, host, backend_port, frontend_port,
                                           **({"protect_credentials": True} if protect_credentials else {})))
        if ready is not None:
            ready(processes)
        print_urls(scope, host, backend_port, frontend_port)
    supervise(processes, **({'health': health} if health is not None else {}))


@windows_lifecycle('prod')
def prod(
    project: Project,
    *,
    host: str,
    port: int,
    env_file: Path,
    certificate_file: Path,
    private_key_file: Path,
    exclude_doors: bool,
    migrate: bool,
    build_frontend: bool = False,
    ready: Callable[[list[subprocess.Popen]], None] | None = None,
    worker_heartbeat_dir: Path | None = None,
    protect_credentials: bool = False,
    health=None,
) -> None:
    """Run the single-host Windows HTTPS production lifecycle."""

    require_windows_production()
    ensure_virtual_environment(project, create=False)
    require_production_host(host)
    require_port(host, port)
    require_external_file(project, env_file, "production environment")
    require_external_file(project, certificate_file, "TLS certificate")
    require_external_file(project, private_key_file, "TLS private key")
    if certificate_file == private_key_file:
        raise LauncherError("TLS certificate and private key must be different files")
    validate_tls_identity(project, certificate_file, private_key_file, host)

    extra_env = production_env(env_file, host, port)
    gate_env = {**extra_env, **non_notification_environment()} if protect_credentials else extra_env
    # Validate the notification worker's real SMTP transport/TLS settings too.
    # Redaction is for non-notification runtime roles, not deployment policy.
    django(project, ["check", "--deploy"], extra_env)
    if migrate:
        django(project, ["migrate", "--noinput"], gate_env)
    django(project, ["migrate", "--check"], gate_env)
    if build_frontend:
        run_script(project, "build")
    django(project, ["collectstatic", "--clear", "--noinput"], gate_env)
    django(project, ["verify_frontend_artifact"], gate_env)

    with starting_processes() as processes:
        processes.append(
            start_production_backend(
                project,
                host,
                port,
                certificate_file,
                private_key_file,
                gate_env,
            )
        )
        processes.extend(
            start_job_workers(
                project,
                extra_env,
                include_doors_if_enabled=not exclude_doors,
                **({"heartbeat_dir": worker_heartbeat_dir} if worker_heartbeat_dir else {}),
                **({"protect_credentials": True} if protect_credentials else {}),
            )
        )
        if ready is not None:
            ready(processes)
        print(f"Production: {production_url(host, port)}")
        print("Press Ctrl+C to stop.")
    supervise(processes, **({'health': health} if health is not None else {}))


def start_production_backend(
    project: Project,
    host: str,
    port: int,
    certificate_file: Path,
    private_key_file: Path,
    extra_env: dict[str, str],
) -> subprocess.Popen:
    """Start one TLS-enabled ASGI server for the SQLite production profile."""

    command = [
        project.python,
        "-m",
        "uvicorn",
        "awcenter.asgi:application",
        "--host",
        host,
        "--port",
        str(port),
        "--ssl-certfile",
        certificate_file,
        "--ssl-keyfile",
        private_key_file,
        "--no-server-header",
        "--timeout-keep-alive",
        "5",
    ]
    return start(command, project.backend, extra_env=extra_env)


def start_backend(
    project: Project, host: str, port: int, frontend_port: int, no_reload: bool, migrate: bool,
    *, protect_credentials: bool = False,
) -> subprocess.Popen:
    """Prepare and start the Django development child."""
    ensure_virtual_environment(project, create=False)
    extra_env = runtime_env(host, port, frontend_port)
    # Only the local job worker performs number allocation; dotenv must not
    # reintroduce the generation credential into the development web process.
    extra_env["NUMARATOR_API_KEY"] = ""
    if protect_credentials:
        extra_env.update(non_notification_environment())
    if migrate:
        django(project, ["migrate", "--noinput"], extra_env)
    command = [project.python, "manage.py", "runserver", f"{host}:{port}"]
    if no_reload:
        command.append("--noreload")
    return start(command, project.backend, extra_env=extra_env)


def start_frontend(
    project: Project, host: str, backend_port: int, port: int, *, protect_credentials: bool = False,
) -> subprocess.Popen:
    """Start the Vue development child with an ephemeral API URL."""
    script = select_script(project, ("dev", "serve", "start"), required=True)
    with frontend_environment(protect_credentials):
        prefix = npm_command() if os.environ.get("AWCENTER_MANAGED_NPM_CLI") else [required_tool("npm")]
        command = [*prefix, "run", script, "--", "--host", host, "--port", str(port)]
        if script == "dev":
            command.append("--strictPort")
        return start(command, project.frontend, extra_env=frontend_env(public_url(host, backend_port)))


def runtime_env(host: str, backend_port: int, frontend_port: int | None) -> dict[str, str]:
    """Return ephemeral runtime overrides without reading or writing env files."""
    values = {"IPV4_ADDRESS": host, "PORT": str(backend_port)}
    if frontend_port is not None:
        values["DEV_FRONTEND_PORT"] = str(frontend_port)
        values["DEV_BACKEND_PORT"] = str(backend_port)
    return values


def production_env(env_file: Path, host: str, port: int) -> dict[str, str]:
    """Select the external production profile and authoritative bind address."""

    return {
        "AWCENTER_ENV_FILE": str(env_file),
        "AWCENTER_DEPLOYMENT_MODE": "windows-native",
        "IPV4_ADDRESS": host,
        "PORT": str(port),
    }


def require_windows_production() -> None:
    """Reject accidental use of the native production command on other platforms."""

    if sys.platform != "win32":
        raise LauncherError("launcher.py prod is supported only on Windows")


def require_production_host(host: str) -> None:
    """Require one explicit, non-loopback IPv4 address for LAN production."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise LauncherError("production host must be a static IPv4 address") from error
    if (
        address.version != 4
        or address.is_unspecified
        or address.is_loopback
        or address.is_multicast
    ):
        raise LauncherError("production host must be a static, non-loopback IPv4 address")


def require_external_file(project: Project, path: Path, label: str) -> None:
    """Require an unlinked regular file outside the source checkout."""

    if path.is_symlink() or not path.is_file():
        raise LauncherError(f"{label} must be an existing regular file: {path}")
    try:
        path.resolve(strict=True).relative_to(project.root.resolve())
    except ValueError:
        return
    raise LauncherError(f"{label} must be stored outside the repository")


def validate_tls_identity(
    project: Project, certificate_file: Path, private_key_file: Path, host: str
) -> None:
    """Use the project interpreter so the launcher itself needs only the standard library."""

    run(
        [project.python, "-m", "scripts.launcher.tls", certificate_file, private_key_file, host],
        project.root,
        capture=True,
    )


def production_url(host: str, port: int) -> str:
    """Return the public same-origin production URL."""

    suffix = "" if port == 443 else f":{port}"
    return f"https://{host}{suffix}"


def frontend_env(backend_url: str) -> dict[str, str]:
    """Expose the backend URL only to the Vite child process."""
    return {"VITE_API_URL": backend_url, "NUMARATOR_API_KEY": ""}


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
    if scope.backend and scope.frontend:
        print(
            "Use the frontend URL exactly as printed; "
            "its hostname is part of the API security check."
        )
    print("Press Ctrl+C to stop.")
