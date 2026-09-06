"""Local development, check, and test workflows."""

from __future__ import annotations

import ipaddress
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from .dependencies import ensure_virtual_environment
from .job_worker import start_job_workers
from .model import LauncherError, Project, Scope
from .process import required_tool, run, start, supervise
from .quality import django, run_first_script, select_script


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
        processes.append(
            start_backend(
                project,
                host,
                backend_port,
                frontend_port,
                no_backend_reload,
                migrate,
            )
        )
        processes.extend(
            start_job_workers(project, runtime_env(host, backend_port, frontend_port))
        )
    if scope.frontend:
        processes.append(start_frontend(project, host, backend_port, frontend_port))
    print_urls(scope, host, backend_port, frontend_port)
    supervise(processes)


def prod(
    project: Project,
    *,
    host: str,
    port: int,
    env_file: Path,
    certificate_file: Path,
    private_key_file: Path,
    include_doors: bool,
    migrate: bool,
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
    validate_tls_identity(certificate_file, private_key_file, host)

    extra_env = production_env(env_file, host, port)
    django(project, ["check", "--deploy"], extra_env)
    if migrate:
        django(project, ["migrate", "--noinput"], extra_env)
    django(project, ["migrate", "--check"], extra_env)
    django(project, ["collectstatic", "--clear", "--noinput"], extra_env)
    django(project, ["verify_frontend_artifact"], extra_env)

    processes = [
        start_production_backend(
            project,
            host,
            port,
            certificate_file,
            private_key_file,
            extra_env,
        )
    ]
    processes.extend(
        start_job_workers(project, extra_env, include_doors=include_doors)
    )
    print(f"Production: {production_url(host, port)}")
    print("Press Ctrl+C to stop.")
    supervise(processes)


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


def validate_tls_identity(certificate_file: Path, private_key_file: Path, host: str) -> None:
    """Require a live certificate/key pair whose SAN contains the static IP."""

    try:
        certificate = x509.load_pem_x509_certificate(certificate_file.read_bytes())
        private_key = serialization.load_pem_private_key(
            private_key_file.read_bytes(), password=None
        )
        certificate_key = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_public_key = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        san = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except (OSError, ValueError, TypeError, x509.ExtensionNotFound) as error:
        raise LauncherError("TLS certificate or private key is invalid") from error
    if certificate_key != private_public_key:
        raise LauncherError("TLS certificate does not match the private key")
    if ipaddress.ip_address(host) not in san.get_values_for_type(x509.IPAddress):
        raise LauncherError("TLS certificate SAN does not contain the production IPv4 address")
    now = datetime.now(timezone.utc)
    if (
        certificate.not_valid_before_utc > now
        or certificate.not_valid_after_utc <= now + timedelta(days=1)
    ):
        raise LauncherError("TLS certificate is not currently valid for production")


def production_url(host: str, port: int) -> str:
    """Return the public same-origin production URL."""

    suffix = "" if port == 443 else f":{port}"
    return f"https://{host}{suffix}"


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
    if scope.backend and scope.frontend:
        print(
            "Use the frontend URL exactly as printed; "
            "its hostname is part of the API security check."
        )
    print("Press Ctrl+C to stop.")
