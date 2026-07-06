#!/usr/bin/env python3
"""Production-oriented launcher for AW Center setup and validation.

USAGE EXAMPLES
==============

Windows / PowerShell
--------------------
Run with Python 3.11 explicitly:

    py -3.11 launcher.py install

Install backend and frontend:

    py -3.11 launcher.py install

Install everything, then run checks:

    py -3.11 launcher.py all

Run checks only:

    py -3.11 launcher.py check

Run checks and automatically create/apply Django migrations when needed:

    py -3.11 launcher.py check --fix-migrations

Full install + checks + automatic migration fix:

    py -3.11 launcher.py all --fix-migrations

Prepare offline Python wheels and npm cache:

    py -3.11 launcher.py prepare-offline

Package only the files needed for offline transfer into a ZIP:

    py -3.11 launcher.py package-offline
    py -3.11 launcher.py package-offline --offline-zip C:\\packages\\aw-center-offline.zip

Package Git changes into a ZIP at the project root:

    py -3.11 launcher.py package-changes
    py -3.11 launcher.py package-changes --changes-zip my-local-changes.zip

Open the interactive menu and choose command/options step by step:

    py -3.11 launcher.py --interactive
    py -3.11 launcher.py -i

Install from prepared offline bundle:

    py -3.11 launcher.py install --mode offline

Use a custom offline bundle directory:

    py -3.11 launcher.py install --mode offline --offline-dir offline
    py -3.11 launcher.py install --mode offline --offline-dir C:\\packages\\aw-center-offline

Backend only:

    py -3.11 launcher.py install --skip-frontend
    py -3.11 launcher.py check --skip-frontend

Frontend only:

    py -3.11 launcher.py install --skip-backend
    py -3.11 launcher.py check --skip-backend

Run backend and frontend development servers:

    py -3.11 launcher.py run

Run with preferred ports. If a port is busy, the launcher automatically tries
the next free port:

    py -3.11 launcher.py run --backend-port 8000 --frontend-port 5173

Run only one side:

    py -3.11 launcher.py run --skip-frontend
    py -3.11 launcher.py run --skip-backend

When both backend and frontend are started, the launcher writes the selected
backend URL to frontend/.env.local so Vite can expose it to the Vue app:

    VITE_API_BASE_URL=http://127.0.0.1:<selected-backend-port>

Unix-like systems
-----------------
Run with Python 3.11 explicitly:

    python3.11 launcher.py install

Full install + checks:

    python3.11 launcher.py all

Checks with migration fix:

    python3.11 launcher.py check --fix-migrations

Notes
-----
- This launcher intentionally uses the Python executable inside the project
  virtual environment for backend commands, for example:

      .venv/Scripts/python.exe manage.py check

  That does NOT mean the working directory is moved into .venv.
- The subprocess working directory is always validated. The launcher refuses to
  execute commands with cwd inside .venv.
- The project root is detected by walking upward and looking for markers such as
  requirements.txt, backend/manage.py, frontend/package.json, and .git.
- `makemigrations --check --dry-run` returning exit code 1 usually means Django
  model changes exist but migration files have not been created yet. Use
  `--fix-migrations` when you want the launcher to create/apply them.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import shlex
import time
import zipfile
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

MINIMUM_PYTHON = (3, 11)
NETWORK_PROBES = ("pypi.org", "registry.npmjs.org")
COMMAND_CHOICES = (
    "prepare-offline",
    "package-offline",
    "package-changes",
    "install",
    "check",
    "all",
    "run",
)
MODE_CHOICES = ("auto", "online", "offline")


def project_score(path: Path) -> int:
    """Score how likely a directory is to be the project root."""
    markers = [
        path / "requirements.txt",
        path / "backend" / "manage.py",
        path / "frontend" / "package.json",
        path / ".git",
    ]
    return sum(marker.exists() for marker in markers)


def find_project_root() -> Path:
    """Find the repository root even when the launcher is started from .venv."""
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    seen: set[Path] = set()
    best_path: Path | None = None
    best_score = 0

    for start in starts:
        resolved_start = start.resolve()
        candidates = (resolved_start, *resolved_start.parents)

        for candidate in candidates:
            if candidate in seen:
                continue

            seen.add(candidate)
            score = project_score(candidate)

            if score > best_score:
                best_score = score
                best_path = candidate

    if best_path is not None and best_score >= 2:
        return best_path

    raise RuntimeError(
        "Project root could not be detected. Run this file from the repository, "
        "or keep it somewhere under the repository that contains backend/manage.py, "
        "frontend/package.json, or requirements.txt."
    )


ROOT = find_project_root()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
OFFLINE = ROOT / "offline"
REQUIREMENTS = ROOT / "requirements.txt"


@dataclass(frozen=True)
class LauncherConfig:
    """Runtime configuration selected from command-line arguments."""

    command: str
    mode: str
    offline_dir: Path
    offline_zip: Path
    changes_zip: Path
    skip_frontend: bool
    skip_backend: bool
    fix_migrations: bool
    host: str
    backend_port: int
    frontend_port: int
    no_backend_reload: bool


def executable(name: str) -> str:
    """Return a platform-specific executable name."""
    return f"{name}.exe" if os.name == "nt" else name


def required_tool(name: str) -> str:
    """Return an executable path or fail with a clear message."""
    candidates = [name]

    if os.name == "nt":
        candidates = [f"{name}.cmd", f"{name}.exe", name]

    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found

    raise RuntimeError(f"required tool is missing on PATH: {name}")


def npm_command() -> str:
    """Return the platform-specific npm executable path."""
    return required_tool("npm")


def ensure_node_and_npm() -> None:
    """Fail early when frontend tooling is unavailable."""
    required_tool("node")
    required_tool("npm")


def venv_python() -> Path:
    """Return the project virtual-environment Python executable."""
    return VENV / ("Scripts" if os.name == "nt" else "bin") / executable("python")


def format_python_version(version: tuple[int, int, int]) -> str:
    """Return a human-readable Python version string."""
    return ".".join(str(part) for part in version)


def ensure_python_version(version: tuple[int, int, int], source: str) -> None:
    """Fail when a Python interpreter is older than the supported minimum."""
    if version[:2] >= MINIMUM_PYTHON:
        return

    minimum = ".".join(str(part) for part in MINIMUM_PYTHON)
    current = format_python_version(version)

    raise RuntimeError(
        f"{source} uses Python {current}; Python {minimum}+ is required. "
        "On Windows run: py -3.11 launcher.py install. "
        "On Unix-like systems run: python3.11 launcher.py install."
    )


def current_python_version() -> tuple[int, int, int]:
    """Return the Python version running this launcher."""
    return sys.version_info[:3]


def base_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a clean subprocess environment."""
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONNOUSERSITE", "1")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")

    if extra:
        env.update({key: str(value) for key, value in extra.items()})

    return env


def path_is_inside(child: Path, parent: Path) -> bool:
    """Return True if child is equal to or inside parent."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def format_command(command: Sequence[str | Path]) -> str:
    """Return a readable command line for logging."""
    return shlex.join(str(part) for part in command)


def validate_working_directory(cwd: Path | None = None) -> Path:
    """Return a safe working directory for subprocess execution."""
    working_dir = (cwd or ROOT).resolve()

    if path_is_inside(working_dir, VENV):
        raise RuntimeError(
            f"Refusing to run inside virtual environment directory: {working_dir}. "
            f"Project root is: {ROOT}"
        )

    if not working_dir.exists():
        raise RuntimeError(f"working directory does not exist: {working_dir}")

    return working_dir


def run(command: Sequence[str | Path], cwd: Path | None = None) -> None:
    """Run a subprocess without ever using .venv as the working directory."""
    working_dir = validate_working_directory(cwd)
    argv = [str(part) for part in command]

    print(f"\n[{working_dir}]$ {format_command(command)}")

    completed = subprocess.run(
        argv,
        cwd=str(working_dir),
        env=base_env(),
        check=False,
    )

    if completed.returncode:
        raise RuntimeError(
            f"command failed with exit code {completed.returncode}\n"
            f"cwd     : {working_dir}\n"
            f"command : {format_command(command)}"
        )


def run_result(
    command: Sequence[str | Path],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return stdout/stderr for smart handling."""
    working_dir = validate_working_directory(cwd)
    argv = [str(part) for part in command]

    print(f"\n[{working_dir}]$ {format_command(command)}")

    completed = subprocess.run(
        argv,
        cwd=str(working_dir),
        env=base_env(),
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.stdout:
        print(completed.stdout.rstrip())

    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)

    return completed


def is_tcp_port_free(host: str, port: int) -> bool:
    """Return True when host:port can be used by a new local server."""
    if port <= 0 or port > 65535:
        return False

    # First check whether something is already accepting connections.
    # Then try to bind without SO_REUSEADDR, because on some platforms that
    # flag can hide an actual port conflict.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        try:
            if probe.connect_ex((host, port)) == 0:
                return False
        except OSError:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as binder:
        try:
            binder.bind((host, port))
        except OSError:
            return False

    return True


def find_free_port(
    host: str,
    preferred_port: int,
    *,
    reserved_ports: set[int] | None = None,
    max_attempts: int = 200,
) -> int:
    """Return preferred_port or the next available TCP port."""
    reserved = reserved_ports or set()

    for port in range(preferred_port, min(65535, preferred_port + max_attempts) + 1):
        if port in reserved:
            continue

        if is_tcp_port_free(host, port):
            if port != preferred_port:
                print(f"WARN: {host}:{preferred_port} is busy; using {host}:{port} instead.")
            return port

    raise RuntimeError(
        f"No free port found for {host}, starting at {preferred_port} "
        f"after {max_attempts} attempts."
    )


def update_env_values(env_file: Path, values: dict[str, str]) -> None:
    """Update selected KEY=value entries while preserving the rest of the .env file."""
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    remaining = dict(values)
    updated_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue

        key = line.split("=", 1)[0].strip()

        if key in remaining:
            updated_lines.append(f"{key}={remaining.pop(key)}")
        else:
            updated_lines.append(line)

    for key, value in remaining.items():
        updated_lines.append(f"{key}={value}")

    env_file.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def configure_backend_runtime_env(host: str, port: int) -> None:
    """Make backend .env consistent with the selected runtime address."""
    write_development_env()

    allowed_hosts = ["127.0.0.1", "localhost"]

    if host not in allowed_hosts:
        allowed_hosts.append(host)

    update_env_values(
        BACKEND / ".env",
        {
            "IPV4_ADDRESS": host,
            "PORT": str(port),
            "ALLOWED_HOSTS": ",".join(allowed_hosts),
        },
    )


def configure_frontend_runtime_env(host: str, backend_port: int) -> None:
    """Write the selected backend URL for Vite/Vue development builds."""
    ensure_frontend_layout()

    backend_url = f"http://{host}:{backend_port}"
    env_file = FRONTEND / ".env.local"

    # Vite only exposes variables that start with VITE_.
    # Multiple names are written to support existing code conventions.
    update_env_values(
        env_file,
        {
            "VITE_API_BASE_URL": backend_url,
            "VITE_BACKEND_URL": backend_url,
            "VITE_API_URL": backend_url,
            "VITE_SERVER_URL": backend_url,
        },
    )

    print(f"Frontend env updated: {env_file}")
    print(f"VITE_API_BASE_URL={backend_url}")


def start_process(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    env_extra: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    """Start a long-running subprocess with inherited console output."""
    working_dir = validate_working_directory(cwd)

    print(f"\n[{working_dir}]$ {format_command(command)}")

    return subprocess.Popen(
        [str(part) for part in command],
        cwd=str(working_dir),
        env=base_env(env_extra),
        text=True,
    )


def stop_processes(processes: Sequence[subprocess.Popen[str]]) -> None:
    """Terminate all started development server processes."""
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        if process.poll() is not None:
            continue

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def frontend_dev_script() -> str:
    """Return the frontend development script name."""
    scripts = package_scripts()

    for script in ("dev", "serve", "start"):
        if script in scripts:
            return script

    raise RuntimeError(
        "No frontend development script found in frontend/package.json. "
        "Expected one of: dev, serve, start."
    )


def run_development_servers(config: LauncherConfig) -> None:
    """Run backend and frontend development servers with port conflict protection."""
    if config.skip_backend and config.skip_frontend:
        raise RuntimeError("Nothing to run because both --skip-backend and --skip-frontend were used.")

    selected_backend_port: int | None = None
    selected_frontend_port: int | None = None
    reserved_ports: set[int] = set()

    if not config.skip_backend:
        ensure_backend_layout()
        ensure_existing_virtual_environment()
        selected_backend_port = find_free_port(
            config.host,
            config.backend_port,
            reserved_ports=reserved_ports,
        )
        reserved_ports.add(selected_backend_port)
        configure_backend_runtime_env(config.host, selected_backend_port)

    if not config.skip_frontend:
        ensure_frontend_layout()
        ensure_node_and_npm()
        selected_frontend_port = find_free_port(
            config.host,
            config.frontend_port,
            reserved_ports=reserved_ports,
        )
        reserved_ports.add(selected_frontend_port)

        if selected_backend_port is not None:
            configure_frontend_runtime_env(config.host, selected_backend_port)

    processes: list[subprocess.Popen[str]] = []

    if selected_backend_port is not None:

        backend_command = [
            venv_python(),
            "manage.py",
            "runserver",
            f"{config.host}:{selected_backend_port}",
        ]

        if config.no_backend_reload:
            backend_command.append("--noreload")
        
        processes.append(
            start_process(
                backend_command,
                cwd=BACKEND,
                env_extra={
                    "IPV4_ADDRESS": config.host,
                    "PORT": str(selected_backend_port),
                },
            )
        )

    if selected_frontend_port is not None:
        script = frontend_dev_script()
        frontend_args: list[str | Path] = [
            npm_command(),
            "run",
            script,
            "--",
            "--host",
            config.host,
            "--port",
            str(selected_frontend_port),
        ]

        if script == "dev":
            frontend_args.append("--strictPort")

        processes.append(
            start_process(
                frontend_args,
                cwd=FRONTEND,
                env_extra=(
                    {
                        "VITE_API_BASE_URL": f"http://{config.host}:{selected_backend_port}",
                        "VITE_BACKEND_URL": f"http://{config.host}:{selected_backend_port}",
                        "VITE_API_URL": f"http://{config.host}:{selected_backend_port}",
                        "VITE_SERVER_URL": f"http://{config.host}:{selected_backend_port}",
                    }
                    if selected_backend_port is not None
                    else None
                ),
            )
        )

    print("\nDevelopment servers started.")
    if selected_backend_port is not None:
        print(f"Backend : http://{config.host}:{selected_backend_port}")

    if selected_frontend_port is not None:
        print(f"Frontend: http://{config.host}:{selected_frontend_port}")

    print("\nPress Ctrl+C to stop.")

    try:
        while processes:
            for process in processes:
                return_code = process.poll()

                if return_code is not None:
                    stop_processes(processes)
                    raise RuntimeError(f"A development server stopped with exit code {return_code}.")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping development servers...")
        stop_processes(processes)


def virtual_environment_version() -> tuple[int, int, int]:
    """Return the Python version inside the project virtual environment."""
    version_script = "import sys; print('.'.join(map(str, sys.version_info[:3])))"

    completed = subprocess.run(
        [str(venv_python()), "-c", version_script],
        cwd=str(ROOT),
        env=base_env(),
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode:
        raise RuntimeError(
            "could not determine .venv Python version. "
            "Delete .venv and rerun the launcher with Python 3.11+."
        )

    output = completed.stdout.strip()

    if not output:
        raise RuntimeError(".venv Python version command returned no output")

    return tuple(int(part) for part in output.split("."))


def ensure_backend_layout() -> None:
    """Fail if required backend files are missing."""
    if not (BACKEND / "manage.py").is_file():
        raise RuntimeError(f"backend/manage.py not found under project root: {ROOT}")

    if not REQUIREMENTS.is_file():
        raise RuntimeError(f"requirements.txt not found under project root: {ROOT}")


def ensure_frontend_layout() -> None:
    """Fail if required frontend files are missing."""
    if not (FRONTEND / "package.json").is_file():
        raise RuntimeError(f"frontend/package.json not found under project root: {ROOT}")


def directory_has_files(path: Path) -> bool:
    """Return whether a directory contains at least one file."""
    return path.is_dir() and any(item.is_file() for item in path.rglob("*"))


def offline_backend_ready(offline_dir: Path) -> bool:
    """Return whether offline Python wheels exist."""
    return directory_has_files(offline_dir / "wheels")


def offline_frontend_ready(offline_dir: Path) -> bool:
    """Return whether an offline npm cache exists."""
    return directory_has_files(offline_dir / "npm-cache")


def offline_bundle_ready(offline_dir: Path) -> bool:
    """Return whether any offline bundle content exists."""
    return offline_backend_ready(offline_dir) or offline_frontend_ready(offline_dir)


def ensure_virtual_environment() -> None:
    """Create the project virtual environment when needed."""
    ensure_python_version(current_python_version(), "launcher interpreter")

    if VENV.exists() and not venv_python().exists():
        raise RuntimeError(
            f"{VENV} exists, but its Python executable is missing. "
            "Delete .venv and rerun the launcher."
        )

    if venv_python().exists():
        ensure_python_version(virtual_environment_version(), "existing .venv")
        return

    run([sys.executable, "-m", "venv", VENV], cwd=ROOT)
    ensure_python_version(virtual_environment_version(), "created .venv")


def ensure_existing_virtual_environment() -> None:
    """Require an already-created virtual environment for check-only workflows."""
    if not venv_python().exists():
        raise RuntimeError(
            ".venv does not exist. Run 'launcher.py install' or 'launcher.py all' first."
        )

    ensure_python_version(virtual_environment_version(), "existing .venv")


def pip_install_command(config: LauncherConfig) -> list[str | Path]:
    """Build the pip install command for online or offline mode."""
    command: list[str | Path] = [venv_python(), "-m", "pip", "install"]

    if config.mode == "offline":
        command += ["--no-index", "--find-links", config.offline_dir / "wheels"]

    return command + ["-r", REQUIREMENTS]


def install_backend(config: LauncherConfig) -> None:
    """Install backend dependencies according to the selected mode."""
    if config.skip_backend:
        print("SKIP: backend install")
        return

    ensure_backend_layout()
    ensure_virtual_environment()

    if config.mode == "offline":
        if not offline_backend_ready(config.offline_dir):
            raise RuntimeError(
                f"offline Python wheels not found in {config.offline_dir / 'wheels'}. "
                "Run 'launcher.py prepare-offline' while online."
            )
    else:
        run(
            [
                venv_python(),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "setuptools",
                "wheel",
            ],
            cwd=ROOT,
        )

    run(pip_install_command(config), cwd=ROOT)
    run([venv_python(), "-m", "pip", "check"], cwd=ROOT)


def frontend_uses_lockfile() -> bool:
    """Return whether npm ci can be used safely."""
    return (FRONTEND / "package-lock.json").is_file()


def frontend_install_command(
    config: LauncherConfig,
    *,
    preparing_cache: bool = False,
) -> list[str | Path]:
    """Build the npm install command for online or offline mode."""
    command: list[str | Path] = [
        npm_command(),
        "ci" if frontend_uses_lockfile() else "install",
    ]

    if not frontend_uses_lockfile():
        print(
            "WARN: frontend/package-lock.json not found; "
            "using 'npm install' instead of 'npm ci'."
        )

    if config.mode == "offline":
        command += ["--offline", "--cache", config.offline_dir / "npm-cache"]
    elif preparing_cache:
        command += ["--cache", config.offline_dir / "npm-cache", "--prefer-offline"]

    return command


def install_frontend(config: LauncherConfig) -> None:
    """Install frontend dependencies for online or prepared offline use."""
    if config.skip_frontend:
        print("SKIP: frontend install")
        return

    ensure_frontend_layout()
    ensure_node_and_npm()

    if config.mode == "offline" and not offline_frontend_ready(config.offline_dir):
        raise RuntimeError(
            f"offline npm cache not found in {config.offline_dir / 'npm-cache'}. "
            "Run 'launcher.py prepare-offline' while online."
        )

    run(frontend_install_command(config), cwd=FRONTEND)


def is_online(timeout_seconds: float = 2.0) -> bool:
    """Return whether a short package-index network probe succeeds."""
    for host in NETWORK_PROBES:
        try:
            with socket.create_connection((host, 443), timeout_seconds):
                return True
        except OSError:
            continue

    return False


def prepare_offline_bundle(config: LauncherConfig) -> None:
    """Download Python wheels and populate npm cache for offline installs."""
    if not is_online():
        print(
            "WARN: direct internet probe failed. Continuing anyway; "
            "pip/npm may still work through a configured proxy or internal registry."
        )

    if not config.skip_backend:
        ensure_backend_layout()
        ensure_virtual_environment()

        (config.offline_dir / "wheels").mkdir(parents=True, exist_ok=True)

        run(
            [
                venv_python(),
                "-m",
                "pip",
                "download",
                "--prefer-binary",
                "-r",
                REQUIREMENTS,
                "-d",
                config.offline_dir / "wheels",
            ],
            cwd=ROOT,
        )

    if not config.skip_frontend:
        ensure_frontend_layout()
        ensure_node_and_npm()

        (config.offline_dir / "npm-cache").mkdir(parents=True, exist_ok=True)

        online_config = LauncherConfig(
            command=config.command,
            mode="online",
            offline_dir=config.offline_dir,
            offline_zip=config.offline_zip,
            changes_zip=config.changes_zip,
            skip_frontend=config.skip_frontend,
            skip_backend=config.skip_backend,
            fix_migrations=config.fix_migrations,
            host=config.host,
            backend_port=config.backend_port,
            frontend_port=config.frontend_port,
            no_backend_reload=config.no_backend_reload
        )

        run(
            frontend_install_command(online_config, preparing_cache=True),
            cwd=FRONTEND,
        )

    print(f"\nOffline bundle prepared under: {config.offline_dir}")


OFFLINE_PACKAGE_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".vite",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "htmlcov",
    "coverage",
    "logs",
    "log",
    "media",
    "uploads",
    "tmp",
    "temp",
}

OFFLINE_PACKAGE_EXCLUDED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.development.local",
    ".env.production.local",
    ".DS_Store",
    "Thumbs.db",
    "db.sqlite3",
    "db.sqlite3-journal",
}

OFFLINE_PACKAGE_EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".temp",
    ".swp",
}

ROOT_REQUIRED_FILE_NAMES = {
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-prod.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
}


def path_relative_to_root(path: Path) -> Path:
    """Return path relative to the project root when possible."""
    try:
        return path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return Path(path.name)


def archive_path_for_file(path: Path, config: LauncherConfig) -> Path:
    """Return a stable ZIP path that works after extraction on an offline machine."""
    resolved_path = path.resolve()

    try:
        return resolved_path.relative_to(ROOT.resolve())
    except ValueError:
        pass

    try:
        return Path("offline") / resolved_path.relative_to(config.offline_dir.resolve())
    except ValueError:
        return Path(resolved_path.name)


def should_exclude_from_offline_package(path: Path, output_zip: Path) -> bool:
    """Return True for files/directories that should not be transferred offline."""
    if path.resolve() == output_zip.resolve():
        return True

    relative = path_relative_to_root(path)
    parts = set(relative.parts)

    if parts.intersection(OFFLINE_PACKAGE_EXCLUDED_DIRECTORIES):
        return True

    if path.name in OFFLINE_PACKAGE_EXCLUDED_FILENAMES:
        return True

    if path.suffix.lower() in OFFLINE_PACKAGE_EXCLUDED_SUFFIXES:
        return True

    return False


def iter_package_files(root: Path, output_zip: Path) -> list[Path]:
    """Return packageable files from a file or directory root."""
    if not root.exists():
        return []

    if should_exclude_from_offline_package(root, output_zip):
        return []

    if root.is_file():
        return [root]

    files: list[Path] = []

    for item in root.rglob("*"):
        if item.is_dir():
            continue

        if should_exclude_from_offline_package(item, output_zip):
            continue

        files.append(item)

    return files


def offline_package_roots(config: LauncherConfig) -> list[Path]:
    """Return only the roots needed to recreate/install the project offline."""
    roots: list[Path] = []

    # Include the launcher currently being executed so the offline machine gets
    # the exact same install/check/run commands.
    roots.append(Path(__file__).resolve())

    for file_name in ROOT_REQUIRED_FILE_NAMES:
        candidate = ROOT / file_name
        if candidate.exists():
            roots.append(candidate)

    if not config.skip_backend:
        ensure_backend_layout()
        if not offline_backend_ready(config.offline_dir):
            raise RuntimeError(
                f"offline Python wheels not found in {config.offline_dir / 'wheels'}. "
                "Run 'launcher.py prepare-offline' first, or use --skip-backend."
            )
        roots.append(BACKEND)
        roots.append(config.offline_dir / "wheels")

    if not config.skip_frontend:
        ensure_frontend_layout()
        if not offline_frontend_ready(config.offline_dir):
            raise RuntimeError(
                f"offline npm cache not found in {config.offline_dir / 'npm-cache'}. "
                "Run 'launcher.py prepare-offline' first, or use --skip-frontend."
            )
        roots.append(FRONTEND)
        roots.append(config.offline_dir / "npm-cache")

    # Preserve deterministic order and avoid duplicate roots.
    unique_roots: list[Path] = []
    seen: set[Path] = set()

    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_roots.append(resolved)

    return unique_roots


def package_offline_bundle(config: LauncherConfig) -> None:
    """Create a ZIP containing only the files needed by the offline environment."""
    output_zip = config.offline_zip.resolve()
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    roots = offline_package_roots(config)
    files: list[Path] = []

    for root in roots:
        files.extend(iter_package_files(root, output_zip))

    unique_files: list[Path] = []
    seen: set[Path] = set()

    for file_path in files:
        resolved = file_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(resolved)

    if not unique_files:
        raise RuntimeError("No files found to package for offline transfer.")

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(unique_files, key=lambda item: archive_path_for_file(item, config).as_posix()):
            archive.write(file_path, archive_path_for_file(file_path, config).as_posix())

    total_size = sum(file_path.stat().st_size for file_path in unique_files)

    print(f"\nOffline ZIP created: {output_zip}")
    print(f"Included files    : {len(unique_files)}")
    print(f"Source size       : {total_size / (1024 * 1024):.2f} MB")
    print(f"ZIP size          : {output_zip.stat().st_size / (1024 * 1024):.2f} MB")
    print("\nTransfer this ZIP to the offline machine, extract it, then run:")
    print("  py -3.11 launcher.py install --mode offline")




def git_repository_root() -> Path:
    """Return the Git repository root for the detected project root."""
    if not (ROOT / ".git").exists():
        raise RuntimeError(f"No .git directory found under project root: {ROOT}")

    git = required_tool("git")
    completed = subprocess.run(
        [git, "rev-parse", "--show-toplevel"],
        cwd=str(ROOT),
        env=base_env(),
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Project root is not a readable Git repository: {detail}")

    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("git rev-parse returned an empty repository root")

    return Path(output).resolve()


def git_status_changed_paths(repo_root: Path) -> list[Path]:
    """Return changed, staged, unstaged, and untracked files from Git status."""
    git = required_tool("git")
    completed = subprocess.run(
        [git, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=str(repo_root),
        env=base_env(),
        check=False,
        capture_output=True,
    )

    if completed.returncode:
        stderr = completed.stderr.decode(errors="replace").strip()
        stdout = completed.stdout.decode(errors="replace").strip()
        detail = stderr or stdout or "git status failed"
        raise RuntimeError(detail)

    entries = completed.stdout.split(b"\0")
    changed_paths: list[Path] = []
    index = 0

    while index < len(entries):
        raw_entry = entries[index]
        index += 1

        if not raw_entry:
            continue

        entry = raw_entry.decode(errors="surrogateescape")

        if len(entry) < 4:
            continue

        status = entry[:2]
        relative_path = entry[3:]

        # In porcelain v1 -z, rename/copy entries store the current path first,
        # followed by the old path as the next NUL-delimited field.
        if any(flag in status for flag in ("R", "C")) and index < len(entries):
            index += 1

        # Deleted files cannot be archived, but modified/added/untracked files can.
        if status in {" D", "D ", "DD"}:
            continue

        changed_paths.append((repo_root / relative_path).resolve())

    unique_paths: list[Path] = []
    seen: set[Path] = set()

    for path in changed_paths:
        if path in seen:
            continue

        seen.add(path)
        unique_paths.append(path)

    return unique_paths


def default_changes_zip_path() -> Path:
    """Return a timestamped Git changes ZIP path under the project root."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT / f"git-changes-{timestamp}.zip"


def resolve_changes_zip(value: str | None) -> Path:
    """Resolve Git changes ZIP output path relative to the project root."""
    if not value:
        return default_changes_zip_path().resolve()

    path = Path(value).expanduser()

    if not path.is_absolute():
        path = ROOT / path

    return path.resolve()


def package_git_changes(config: LauncherConfig) -> None:
    """Package Git changed files into a ZIP while preserving project-root paths."""
    repo_root = git_repository_root()
    changed_paths = git_status_changed_paths(repo_root)
    output_zip = config.changes_zip.resolve()
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    packageable_files: list[Path] = []
    skipped_paths: list[Path] = []

    for path in changed_paths:
        if not path_is_inside(path, ROOT):
            skipped_paths.append(path)
            continue

        if path.resolve() == output_zip:
            continue

        if not path.is_file():
            skipped_paths.append(path)
            continue

        packageable_files.append(path)

    if not packageable_files:
        print("\nNo Git-changed files found to package.")
        if skipped_paths:
            print(f"Skipped paths      : {len(skipped_paths)}")
        return

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(packageable_files, key=lambda item: item.relative_to(ROOT).as_posix()):
            archive.write(file_path, file_path.relative_to(ROOT).as_posix())

    total_size = sum(file_path.stat().st_size for file_path in packageable_files)

    print(f"\nGit changes ZIP created: {output_zip}")
    print(f"Included files         : {len(packageable_files)}")
    print(f"Source size            : {total_size / (1024 * 1024):.2f} MB")
    print(f"ZIP size               : {output_zip.stat().st_size / (1024 * 1024):.2f} MB")

    if skipped_paths:
        print(f"Skipped paths          : {len(skipped_paths)}")


def development_env_content() -> str:
    """Return non-secret development defaults for Django checks."""
    lines = [
        "DEBUG=True",
        "SECRET_KEY=dev-insecure-secret-key-change-me",
        "IPV4_ADDRESS=127.0.0.1",
        "PORT=8000",
        "DOCPROOF_URL=http://localhost:9000",
        "DOORS_EXECUTABLE=doors",
        "JIRA_LEGACY_URL=http://localhost:8080",
        "JIRA_BTB_URL=http://localhost:8080",
        "AW_USERNAME=",
        "AW_PASSWORD=",
        "ALLOWED_HOSTS=127.0.0.1,localhost",
        "",
    ]

    return "\n".join(lines)


def write_development_env() -> None:
    """Create a safe local backend .env file if it is absent."""
    ensure_backend_layout()

    env_file = BACKEND / ".env"

    if env_file.exists():
        return

    env_file.write_text(development_env_content(), encoding="utf-8")
    print(f"Created development env file: {env_file}")


def check_backend_database(config: LauncherConfig) -> None:
    """Run Django system, migration, and database consistency checks."""
    ensure_backend_layout()
    ensure_existing_virtual_environment()
    write_development_env()

    python = venv_python()

    run([python, "manage.py", "check"], cwd=BACKEND)

    migration_check = run_result(
        [python, "manage.py", "makemigrations", "--check", "--dry-run"],
        cwd=BACKEND,
    )

    if migration_check.returncode:
        if config.fix_migrations:
            print("\nMissing Django migration files detected. Creating migrations...")
            run([python, "manage.py", "makemigrations"], cwd=BACKEND)
        else:
            raise RuntimeError(
                "Django model changes require new migration files.\n"
                "Run one of these commands:\n\n"
                "  py -3.11 launcher.py check --fix-migrations\n"
                "  py -3.11 launcher.py all --fix-migrations\n\n"
                "or manually:\n\n"
                "  cd backend\n"
                "  ..\\.venv\\Scripts\\python.exe manage.py makemigrations\n"
            )

    migrate_check = run_result(
        [python, "manage.py", "migrate", "--check"],
        cwd=BACKEND,
    )

    if migrate_check.returncode:
        if config.fix_migrations:
            print("\nUnapplied Django migrations detected. Applying migrations...")
            run([python, "manage.py", "migrate"], cwd=BACKEND)
        else:
            raise RuntimeError(
                "There are unapplied Django migrations.\n"
                "Run one of these commands:\n\n"
                "  py -3.11 launcher.py check --fix-migrations\n"
                "  py -3.11 launcher.py all --fix-migrations\n\n"
                "or manually:\n\n"
                "  cd backend\n"
                "  ..\\.venv\\Scripts\\python.exe manage.py migrate\n"
            )


def package_scripts() -> dict[str, str]:
    """Return frontend package.json scripts."""
    ensure_frontend_layout()

    try:
        data = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"frontend/package.json is invalid JSON: {error}") from error

    scripts = data.get("scripts", {})

    return scripts if isinstance(scripts, dict) else {}


def run_first_existing_npm_script(candidates: Sequence[str], label: str) -> None:
    """Run the first available npm script from a candidate list."""
    scripts = package_scripts()

    for script in candidates:
        if script in scripts:
            run([npm_command(), "run", script], cwd=FRONTEND)
            return

    print(f"SKIP: no frontend {label} script found. Tried: {', '.join(candidates)}")


def check_frontend() -> None:
    """Run repository-owned frontend validation commands when present."""
    ensure_frontend_layout()
    ensure_node_and_npm()

    run_first_existing_npm_script(
        ["format:check", "format-check", "lint:format"],
        "format check",
    )

    run_first_existing_npm_script(
        ["typecheck:ci", "typecheck", "type-check"],
        "typecheck",
    )


def validate_project(config: LauncherConfig) -> None:
    """Validate dependencies, Django database state, and frontend health."""
    install_backend(config)
    install_frontend(config)

    if not config.skip_backend:
        check_backend_database(config)

    if not config.skip_frontend:
        check_frontend()


def detect_mode(requested_mode: str, offline_dir: Path) -> str:
    """Resolve auto mode to online or offline using network and bundle checks."""
    if requested_mode != "auto":
        return requested_mode

    if is_online():
        return "online"

    if offline_bundle_ready(offline_dir):
        return "offline"

    print(
        "WARN: network probe failed and no offline bundle was found; "
        "trying online mode because pip/npm may still use configured proxies."
    )

    return "online"


def resolve_offline_dir(value: str) -> Path:
    """Resolve offline directory relative to project root, not .venv or shell cwd."""
    path = Path(value).expanduser()

    if not path.is_absolute():
        path = ROOT / path

    return path.resolve()


def resolve_offline_zip(value: str) -> Path:
    """Resolve offline ZIP output path relative to the project root."""
    path = Path(value).expanduser()

    if not path.is_absolute():
        path = ROOT / path

    return path.resolve()




def resolve_mode_for_command(command: str, requested_mode: str, offline_dir: Path) -> str:
    """Resolve the effective online/offline mode for a launcher command."""
    if command == "prepare-offline":
        return "online"

    if command in {"package-offline", "package-changes", "run"}:
        return requested_mode

    return detect_mode(requested_mode, offline_dir)


def prompt_choice(title: str, choices: Sequence[str], default: str) -> str:
    """Prompt until the user selects one value from a numbered choice list."""
    if default not in choices:
        default = choices[0]

    default_index = choices.index(default) + 1

    while True:
        print(f"\n{title}")
        for index, choice in enumerate(choices, start=1):
            marker = "*" if choice == default else " "
            suffix = "  *" if marker == "*" else ""
            print(f"  {index}) {choice}{suffix}")

        answer = input(f"Selection [{default_index}]: ").strip()

        if not answer:
            return default

        if answer.isdigit():
            numeric_answer = int(answer)
            if 1 <= numeric_answer <= len(choices):
                return choices[numeric_answer - 1]

        lowered = answer.lower()
        for choice in choices:
            if lowered == choice.lower():
                return choice

        print("Invalid selection. Enter a number or one of the shown values.")


def prompt_bool(title: str, default: bool) -> bool:
    """Prompt for a yes/no value."""
    suffix = "Y/n" if default else "y/N"

    while True:
        answer = input(f"{title} [{suffix}]: ").strip().lower()

        if not answer:
            return default

        if answer in {"y", "yes", "e", "evet"}:
            return True

        if answer in {"n", "no", "h", "hayir", "hayır"}:
            return False

        print("Invalid answer. Use yes/no or evet/hayır.")


def prompt_text(title: str, default: str) -> str:
    """Prompt for text with a default value."""
    answer = input(f"{title} [{default}]: ").strip()
    return answer or default


def prompt_int(title: str, default: int) -> int:
    """Prompt for an integer with a default value."""
    while True:
        answer = input(f"{title} [{default}]: ").strip()

        if not answer:
            return default

        try:
            return int(answer)
        except ValueError:
            print("Invalid number. Enter an integer value.")


def frontend_backend_scope(skip_frontend: bool, skip_backend: bool) -> str:
    """Return an interactive scope value from skip flags."""
    if skip_frontend and not skip_backend:
        return "backend-only"

    if skip_backend and not skip_frontend:
        return "frontend-only"

    return "both"


def skip_flags_from_scope(scope: str) -> tuple[bool, bool]:
    """Return skip_frontend and skip_backend flags from an interactive scope value."""
    if scope == "backend-only":
        return True, False

    if scope == "frontend-only":
        return False, True

    return False, False


def interactive_configuration(args: argparse.Namespace) -> LauncherConfig:
    """Build launcher configuration through an interactive menu."""
    print("\nAW Center launcher interactive mode")
    print("Press Enter to keep the value marked with * or shown in brackets.")

    command = prompt_choice(
        "1) Choose the launcher command",
        COMMAND_CHOICES,
        args.command or "run",
    )

    requested_mode = prompt_choice(
        "2) Choose dependency/install mode",
        MODE_CHOICES,
        args.mode,
    )

    offline_dir_value = prompt_text("3) Offline bundle directory", args.offline_dir)
    offline_zip_value = args.offline_zip
    changes_zip_value = args.changes_zip

    skip_frontend = args.skip_frontend
    skip_backend = args.skip_backend
    fix_migrations = args.fix_migrations
    host = args.host
    backend_port = args.backend_port
    frontend_port = args.frontend_port
    no_backend_reload = args.no_backend_reload

    if command in {"prepare-offline", "package-offline", "install", "check", "all", "run"}:
        scope = prompt_choice(
            "4) Which project side should be included?",
            ("both", "backend-only", "frontend-only"),
            frontend_backend_scope(skip_frontend, skip_backend),
        )
        skip_frontend, skip_backend = skip_flags_from_scope(scope)

    if command in {"check", "all"}:
        fix_migrations = prompt_bool("Create/apply missing Django migrations automatically?", fix_migrations)

    if command == "package-offline":
        offline_zip_value = prompt_text("Offline ZIP output path", offline_zip_value)

    if command == "package-changes":
        default_changes = changes_zip_value or str(default_changes_zip_path())
        changes_zip_value = prompt_text("Git changes ZIP output path", default_changes)

    if command == "run":
        host = prompt_text("Development server host", host)
        backend_port = prompt_int("Preferred backend port", backend_port)
        frontend_port = prompt_int("Preferred frontend port", frontend_port)

    offline_dir = resolve_offline_dir(offline_dir_value)
    offline_zip = resolve_offline_zip(offline_zip_value)
    changes_zip = resolve_changes_zip(changes_zip_value)
    mode = resolve_mode_for_command(command, requested_mode, offline_dir)

    config = LauncherConfig(
        command=command,
        mode=mode,
        offline_dir=offline_dir,
        offline_zip=offline_zip,
        changes_zip=changes_zip,
        skip_frontend=skip_frontend,
        skip_backend=skip_backend,
        fix_migrations=fix_migrations,
        host=host,
        backend_port=backend_port,
        frontend_port=frontend_port,
        no_backend_reload=no_backend_reload
    )

    print("\nSelected configuration")
    print(f"  Command       : {config.command}")
    print(f"  Mode          : {config.mode}")
    print(f"  Offline dir   : {config.offline_dir}")
    print(f"  Offline ZIP   : {config.offline_zip}")
    print(f"  Changes ZIP   : {config.changes_zip}")
    print(f"  Skip backend  : {config.skip_backend}")
    print(f"  Skip frontend : {config.skip_frontend}")
    print(f"  Fix migrations: {config.fix_migrations}")
    print(f"  Host          : {config.host}")
    print(f"  Backend port  : {config.backend_port}")
    print(f"  Frontend port : {config.frontend_port}")
    print(f"  No backend reload: {config.no_backend_reload}")

    if not prompt_bool("Run with these settings?", True):
        raise RuntimeError("Interactive launcher run was cancelled by the user.")

    return config


def parse_arguments() -> LauncherConfig:
    """Parse command-line arguments into launcher configuration."""
    parser = argparse.ArgumentParser(description="AW Center launcher")
    parser.add_argument("command", nargs="?", choices=COMMAND_CHOICES)
    parser.add_argument("--interactive", "-i", action="store_true", help="Open an interactive menu for all launcher options.")
    parser.add_argument("--mode", choices=MODE_CHOICES, default="auto")
    parser.add_argument("--offline-dir", default=str(OFFLINE))
    parser.add_argument(
        "--offline-zip",
        default=str(ROOT / "aw-center-offline.zip"),
        help="ZIP file created by package-offline. Default: aw-center-offline.zip",
    )
    parser.add_argument(
        "--changes-zip",
        default=None,
        help="ZIP file created by package-changes. Default: git-changes-YYYYMMDD-HHMMSS.zip under the project root.",
    )
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-backend", action="store_true")
    parser.add_argument(
        "--fix-migrations",
        action="store_true",
        help="Create missing Django migrations and apply unapplied migrations.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host/IP address used by development servers. Default: 127.0.0.1",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=8000,
        help="Preferred Django development server port. Default: 8000",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=5173,
        help="Preferred frontend development server port. Default: 5173",
    )

    args = parser.parse_args()

    if args.interactive:
        return interactive_configuration(args)

    if args.command is None:
        parser.error("the following arguments are required: command, or use --interactive/-i")

    offline_dir = resolve_offline_dir(args.offline_dir)
    offline_zip = resolve_offline_zip(args.offline_zip)
    changes_zip = resolve_changes_zip(args.changes_zip)
    mode = resolve_mode_for_command(args.command, args.mode, offline_dir)

    return LauncherConfig(
        command=args.command,
        mode=mode,
        offline_dir=offline_dir,
        offline_zip=offline_zip,
        changes_zip=changes_zip,
        skip_frontend=args.skip_frontend,
        skip_backend=args.skip_backend,
        fix_migrations=args.fix_migrations,
        host=args.host,
        backend_port=args.backend_port,
        frontend_port=args.frontend_port,
        no_backend_reload=args.no_backend_reload,
    )

def main() -> int:
    """Run the requested launcher workflow."""
    try:
        config = parse_arguments()

        print(f"Project root : {ROOT}")
        print(f"Mode         : {config.mode}")
        print(f"Offline dir  : {config.offline_dir}")
        if config.command == "package-offline":
            print(f"Offline ZIP  : {config.offline_zip}")
        if config.command == "package-changes":
            print(f"Changes ZIP  : {config.changes_zip}")

        if config.command == "prepare-offline":
            prepare_offline_bundle(config)

        elif config.command == "package-offline":
            package_offline_bundle(config)

        elif config.command == "package-changes":
            package_git_changes(config)

        elif config.command == "install":
            install_backend(config)
            install_frontend(config)

        elif config.command == "check":
            if not config.skip_backend:
                check_backend_database(config)

            if not config.skip_frontend:
                check_frontend()

        elif config.command == "all":
            validate_project(config)

        elif config.command == "run":
            run_development_servers(config)

        return 0

    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
