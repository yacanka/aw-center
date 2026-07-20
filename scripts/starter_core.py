"""Reusable helpers for the AW Center development starter."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR = ROOT_DIR / ".venv"
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"
BACKEND_ENV_FILE = BACKEND_DIR / ".env"


@dataclass(frozen=True)
class CommandResult:
    """Result object returned by command probes."""

    name: str
    available: bool
    detail: str


def executable_name(name: str) -> str:
    """Return the platform-specific executable name."""
    return f"{name}.exe" if os.name == "nt" else name


def npm_name() -> str:
    """Return the platform-specific npm executable name."""
    return "npm.cmd" if os.name == "nt" else "npm"


def venv_python() -> Path:
    """Return the Python executable inside the project virtual environment."""
    folder = "Scripts" if os.name == "nt" else "bin"
    return VENV_DIR / folder / executable_name("python")


def command_exists(command: str) -> CommandResult:
    """Check whether a command is available on PATH."""
    path = shutil.which(command)
    return CommandResult(command, bool(path), path if path else "not found")


def run_command(command: list[str], cwd: Path = ROOT_DIR, env: dict[str, str] | None = None) -> None:
    """Run a command and raise a readable error when it fails."""
    printable = " ".join(command)
    print(f"\n$ {printable}")
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {printable}")


def create_virtual_environment() -> None:
    """Create the local virtual environment when it is missing."""
    if venv_python().exists():
        print(f"Python virtual environment exists: {VENV_DIR}")
        return
    run_command([sys.executable, "-m", "venv", str(VENV_DIR)])


def install_backend() -> None:
    """Install backend Python packages into .venv."""
    create_virtual_environment()
    python = str(venv_python())
    run_command([python, "-m", "pip", "install", "--upgrade", "pip"])
    run_command([python, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])


def install_frontend() -> None:
    """Install frontend packages using the committed lock file when available."""
    install_command = "ci" if (FRONTEND_DIR / "package-lock.json").exists() else "install"
    run_command([npm_name(), install_command], cwd=FRONTEND_DIR)


def backend_env_template() -> str:
    """Return safe local-development backend environment content."""
    lines = [
        "DEBUG=True",
        "SECRET_KEY=aw-center-local-development-secret-key-change-before-production-2026",
        "IPV4_ADDRESS=127.0.0.1",
        "PORT=8000",
        "DOCPROOF_URL=http://localhost:9000",
        "DOORS_EXECUTABLE=doors",
        "JIRA_LEGACY_URL=http://localhost:8080",
        "JIRA_BTB_URL=http://localhost:8080",
        "AW_USERNAME=",
        "AW_PASSWORD=",
        "ALLOWED_HOSTS=127.0.0.1,localhost",
        "DEV_FRONTEND_PORT=5173",
        "DEV_SERVER_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
        "CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
        "",
    ]
    return "\n".join(lines)


def ensure_backend_env() -> None:
    """Create a safe ignored backend/.env for local development if absent."""
    if BACKEND_ENV_FILE.exists():
        print(f"Backend environment exists: {BACKEND_ENV_FILE}")
        return
    BACKEND_ENV_FILE.write_text(backend_env_template(), encoding="utf-8")
    print(f"Created local-only backend environment: {BACKEND_ENV_FILE}")


def check_environment() -> list[CommandResult]:
    """Check required local toolchain commands."""
    python_result = CommandResult("python", venv_python().exists(), str(venv_python()))
    return [python_result, command_exists("node"), command_exists("npm")]


def print_check_results(results: list[CommandResult]) -> None:
    """Print package and toolchain checker output."""
    for result in results:
        marker = "OK" if result.available else "MISSING"
        print(f"[{marker}] {result.name}: {result.detail}")


def fail_when_missing(results: list[CommandResult]) -> None:
    """Fail fast if a required starter dependency is missing."""
    missing = [result.name for result in results if not result.available]
    if missing:
        raise RuntimeError(f"Missing required tools: {', '.join(missing)}")


def run_backend_checks() -> None:
    """Run Django system checks with the project virtual environment."""
    ensure_backend_env()
    run_command([str(venv_python()), "manage.py", "check"], cwd=BACKEND_DIR)


def start_process(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    """Start a long-running server process."""
    print(f"Starting: {' '.join(command)}")
    return subprocess.Popen(command, cwd=cwd, env=env)


def start_servers(host: str, backend_port: int, frontend_port: int) -> None:
    """Start Django, the durable job worker, and Vue together."""
    ensure_backend_env()
    backend_host = "127.0.0.1" if host == "0.0.0.0" else host
    frontend_env = {**os.environ, "VITE_API_URL": f"http://{backend_host}:{backend_port}"}
    processes = [start_process(backend_command(host, backend_port), BACKEND_DIR)]
    processes.append(start_process(worker_command(), BACKEND_DIR))
    processes.append(start_process(frontend_command(host, frontend_port), FRONTEND_DIR, frontend_env))
    wait_for_servers(processes)


def backend_command(host: str, port: int) -> list[str]:
    """Build the Django development server command."""
    return [str(venv_python()), "manage.py", "runserver", f"{host}:{port}"]


def worker_command() -> list[str]:
    """Build the durable background job worker command."""
    return [str(venv_python()), "manage.py", "run_job_worker", "--poll-interval", "1"]


def frontend_command(host: str, port: int) -> list[str]:
    """Build the Vite development server command."""
    return [npm_name(), "run", "dev", "--", "--host", host, "--port", str(port)]


def wait_for_servers(processes: list[subprocess.Popen]) -> None:
    """Wait for server processes and stop all on interruption or failure."""
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping servers...")
    finally:
        stop_processes(processes)


def stop_processes(processes: list[subprocess.Popen]) -> None:
    """Terminate any server processes that are still running."""
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        if process.poll() is None:
            process.wait(timeout=10)
