#!/usr/bin/env python3
"""Production-oriented launcher for AW Center setup and validation."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
OFFLINE = ROOT / "offline"
REQUIREMENTS = ROOT / "requirements.txt"
MINIMUM_PYTHON = (3, 11)

@dataclass(frozen=True)
class LauncherConfig:
    """Runtime configuration selected from command-line arguments."""

    command: str
    mode: str
    offline_dir: Path
    skip_frontend: bool
    skip_backend: bool

def executable(name: str) -> str:
    """Return a platform-specific executable name."""
    return f"{name}.exe" if os.name == "nt" else name

def npm_command() -> str:
    """Return the platform-specific npm command."""
    return "npm.cmd" if os.name == "nt" else "npm"

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
        "Remove .venv and rerun with py -3.11 launcher.py install on Windows "
        "or python3.11 launcher.py install on Unix-like systems."
    )

def current_python_version() -> tuple[int, int, int]:
    """Return the Python version running this launcher."""
    return sys.version_info[:3]

def virtual_environment_version() -> tuple[int, int, int]:
    """Return the Python version inside the project virtual environment."""
    version_script = "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    completed = subprocess.run(
        [str(venv_python()), "-c", version_script],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError("could not determine .venv Python version")
    return tuple(int(part) for part in completed.stdout.strip().split("."))

def run(command: list[str], cwd: Path = ROOT) -> None:
    """Run a subprocess with safe argument passing and clear failures."""
    print(f"\n$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode:
        raise RuntimeError(f"command failed with exit code {completed.returncode}")

def is_online(timeout_seconds: float = 3.0) -> bool:
    """Return whether a short package-index network probe succeeds."""
    try:
        with socket.create_connection(("pypi.org", 443), timeout_seconds):
            return True
    except OSError:
        return False

def ensure_tool(name: str) -> None:
    """Fail if a required executable is not available on PATH."""
    if not shutil.which(name):
        raise RuntimeError(f"required tool is missing on PATH: {name}")

def ensure_virtual_environment() -> None:
    """Create the local Python virtual environment when needed."""
    ensure_python_version(current_python_version(), "launcher interpreter")
    if venv_python().exists():
        ensure_python_version(virtual_environment_version(), "existing .venv")
        return
    run([sys.executable, "-m", "venv", str(VENV)])

def pip_install_command(config: LauncherConfig) -> list[str]:
    """Build the pip install command for online or offline mode."""
    command = [str(venv_python()), "-m", "pip", "install"]
    if config.mode == "offline":
        command += ["--no-index", "--find-links", str(config.offline_dir / "wheels")]
    return command + ["-r", str(REQUIREMENTS)]

def install_backend(config: LauncherConfig) -> None:
    """Install backend dependencies according to the selected mode."""
    if config.skip_backend:
        return
    ensure_virtual_environment()
    if config.mode == "online":
        run([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip"])
    run(pip_install_command(config))
    run([str(venv_python()), "-m", "pip", "check"])

def install_frontend(config: LauncherConfig) -> None:
    """Install frontend dependencies for online or prepared offline use."""
    if config.skip_frontend:
        return
    ensure_tool("node")
    ensure_tool("npm")
    command = [npm_command(), "ci"]
    if config.mode == "offline":
        command += ["--offline", "--cache", str(config.offline_dir / "npm-cache")]
    run(command, FRONTEND)

def prepare_offline_bundle(config: LauncherConfig) -> None:
    """Download Python wheels and populate npm cache for offline installs."""
    if not is_online():
        raise RuntimeError("offline bundle preparation requires internet access")
    (config.offline_dir / "wheels").mkdir(parents=True, exist_ok=True)
    (config.offline_dir / "npm-cache").mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "pip", "download", "-r", str(REQUIREMENTS),
         "-d", str(config.offline_dir / "wheels")])
    run([npm_command(), "ci", "--cache", str(config.offline_dir / "npm-cache"),
         "--prefer-offline"], FRONTEND)

def write_development_env() -> None:
    """Create a safe local backend .env file if it is absent."""
    env_file = BACKEND / ".env"
    if env_file.exists():
        return
    env_file.write_text(development_env_content(), encoding="utf-8")

def development_env_content() -> str:
    """Return non-secret development defaults for Django checks."""
    lines = ["DEBUG=True", "SECRET_KEY=dev-insecure-secret-key-change-me"]
    lines += ["IPV4_ADDRESS=127.0.0.1", "PORT=8000"]
    lines += ["DOCPROOF_URL=http://localhost:9000", "DOORS_EXECUTABLE=doors"]
    lines += ["JIRA_LEGACY_URL=http://localhost:8080", "JIRA_BTB_URL=http://localhost:8080"]
    lines += ["AW_USERNAME=", "AW_PASSWORD=", "ALLOWED_HOSTS=127.0.0.1,localhost", ""]
    return "\n".join(lines)

def check_backend_database() -> None:
    """Run Django system, migration, and database consistency checks."""
    write_development_env()
    python = str(venv_python())
    run([python, "manage.py", "check"], BACKEND)
    run([python, "manage.py", "makemigrations", "--check", "--dry-run"], BACKEND)
    run([python, "manage.py", "migrate", "--check"], BACKEND)

def check_frontend() -> None:
    """Run repository-owned frontend validation commands."""
    run([npm_command(), "run", "format:check"], FRONTEND)
    run([npm_command(), "run", "typecheck:ci"], FRONTEND)

def validate_project(config: LauncherConfig) -> None:
    """Validate dependencies, Django database state, and frontend health."""
    install_backend(config)
    install_frontend(config)
    if not config.skip_backend:
        check_backend_database()
    if not config.skip_frontend:
        check_frontend()

def detect_mode(requested_mode: str) -> str:
    """Resolve auto mode to online or offline using a small network probe."""
    if requested_mode != "auto":
        return requested_mode
    return "online" if is_online() else "offline"

def parse_arguments() -> LauncherConfig:
    """Parse command-line arguments into launcher configuration."""
    parser = argparse.ArgumentParser(description="AW Center launcher")
    parser.add_argument("command", choices=["prepare-offline", "install", "check", "all"])
    parser.add_argument("--mode", choices=["auto", "online", "offline"], default="auto")
    parser.add_argument("--offline-dir", default=str(OFFLINE))
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-backend", action="store_true")
    args = parser.parse_args()
    mode = "online" if args.command == "prepare-offline" else detect_mode(args.mode)
    return LauncherConfig(
        args.command, mode, Path(args.offline_dir).resolve(), args.skip_frontend, args.skip_backend,
    )

def main() -> int:
    """Run the requested launcher workflow."""
    config = parse_arguments()
    try:
        if config.command == "prepare-offline":
            prepare_offline_bundle(config)
        elif config.command == "install":
            install_backend(config)
            install_frontend(config)
        elif config.command == "check":
            check_backend_database()
            check_frontend()
        elif config.command == "all":
            validate_project(config)
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
