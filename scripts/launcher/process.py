"""Safe subprocess execution and foreground process supervision."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Sequence

from .model import LauncherError

Command = Sequence[str | Path]


def environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return the inherited environment with conservative Python defaults."""
    values = os.environ.copy()
    values.setdefault("PYTHONUTF8", "1")
    values.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    if extra:
        values.update({key: str(value) for key, value in extra.items()})
    return values


def required_tool(name: str) -> str:
    """Resolve a tool from PATH or fail with an actionable message."""
    candidates = (f"{name}.cmd", f"{name}.exe", name) if os.name == "nt" else (name,)
    for candidate in candidates:
        if executable := shutil.which(candidate):
            return executable
    raise LauncherError(f"required tool is not available on PATH: {name}")


def display(command: Command) -> str:
    """Format an argument vector without invoking a shell."""
    return shlex.join(str(part) for part in command)


def run(
    command: Command,
    cwd: Path,
    *,
    extra_env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one command and raise a concise error when it fails."""
    print(f"[run] {display(command)}\n      cwd: {cwd}", flush=True)
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        env=environment(extra_env),
        check=False,
        capture_output=capture,
        text=True,
    )
    if completed.returncode:
        raise command_error(command, completed, capture)
    return completed


def command_error(
    command: Command, completed: subprocess.CompletedProcess[str], captured: bool
) -> LauncherError:
    """Build one concise subprocess failure."""
    detail = completed.stderr.strip() if captured else ""
    suffix = f"\n{detail}" if detail else ""
    return LauncherError(f"command failed ({completed.returncode}): {display(command)}{suffix}")


def start(command: Command, cwd: Path, *, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    """Start one foreground child process with inherited output."""
    print(f"[start] {display(command)}\n        cwd: {cwd}", flush=True)
    return subprocess.Popen(
        [str(part) for part in command],
        cwd=cwd,
        env=environment(extra_env),
    )


def supervise(processes: list[subprocess.Popen]) -> None:
    """Wait for child processes and stop siblings on exit or interruption."""
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
        failed = next(process for process in processes if process.poll() is not None)
        raise LauncherError(f"server process exited with code {failed.returncode}")
    except KeyboardInterrupt:
        print("\nStopping servers...")
    finally:
        terminate(processes)


def terminate(processes: Sequence[subprocess.Popen]) -> None:
    """Terminate launcher-owned children without persistent PID state."""
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
