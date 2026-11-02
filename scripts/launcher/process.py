"""Safe subprocess execution and foreground process supervision."""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import sys
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Sequence

from .model import LauncherError

Command = Sequence[str | Path]


def npm_command() -> list[str]:
    """Managed runs bypass CMD parsing entirely, including paths containing '&'."""
    node, cli = os.environ.get("AWCENTER_MANAGED_NODE"), os.environ.get("AWCENTER_MANAGED_NPM_CLI")
    if node and cli:
        return [node, cli]
    return [required_tool("npm")]


def non_notification_environment() -> dict[str, str]:
    """Explicit empties also block dotenv/shared-credential fallback in Django."""
    return {"AWCENTER_MAIL_TRANSPORT": "disabled", "EMAIL_HOST_USER": "", "EMAIL_HOST_PASSWORD": ""}


@contextmanager
def frontend_environment(protect: bool):
    """The frontend needs tool paths, never private Django configuration."""
    if not protect:
        yield
        return
    from .installation_profiles import RELEVANT_KEYS, RELEVANT_PREFIXES
    removed = {key: value for key, value in os.environ.items()
               if key in RELEVANT_KEYS or key.startswith(RELEVANT_PREFIXES) or key.startswith("DJANGO_")}
    # Keep only the two non-secret executable pointers used by npm_command().
    for key in ("AWCENTER_MANAGED_NODE", "AWCENTER_MANAGED_NPM_CLI"):
        removed.pop(key, None)
    try:
        for key in removed:
            os.environ.pop(key, None)
        yield
    finally:
        os.environ.update(removed)


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
    if os.name == "nt":
        return _start_windows(command, cwd, extra_env)
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=cwd,
        env=environment(extra_env),
        start_new_session=True,
    )
    process._launcher_group = process.pid
    return process


def _start_windows(command, cwd, extra_env):
    from .windows_job import WindowsJob

    # The gate prevents the command spawning descendants before containment exists.
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("child_bootstrap.py")),
         *[str(part) for part in command]],
        cwd=cwd, env=environment(extra_env), stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        process._launcher_job = WindowsJob(process._handle)
        process.stdin.write(b"go\n")
        process.stdin.flush()
        process.stdin.close()
        return process
    except BaseException:
        try:
            process.stdin.close()
        finally:
            terminate([process])
        raise


@contextmanager
def starting_processes():
    """Release partially started children when startup fails or is interrupted."""

    processes = []
    try:
        yield processes
    except BaseException:
        terminate(processes)
        raise


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
    """Stop owned trees, including descendants whose original parent exited."""
    for process in processes:
        # Reap exited leaders first: macOS rejects signalling zombie-only groups.
        process.poll()
        job = getattr(process, "_launcher_job", None)
        group = getattr(process, "_launcher_group", None)
        if job is not None:
            job.terminate()
        elif group is not None:
            _signal_group(group, signal.SIGTERM)
        elif process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
    # Give worker shutdown time to close its independently isolated executor tree.
    deadline = time.monotonic() + 30
    for process in processes:
        job = getattr(process, "_launcher_job", None)
        if job is not None:
            try:
                job.wait_for_exit(max(0, deadline - time.monotonic()))
            finally:
                job.close()  # Kill-on-close remains the fallback for the entire tree.
                process._launcher_job = None
        if process.poll() is None:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        group = getattr(process, "_launcher_group", None)
        if group is not None:
            _signal_group(group, signal.SIGKILL)
            process._launcher_group = None
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


def _signal_group(group, value):
    try:
        os.killpg(group, value)
    except ProcessLookupError:
        pass
