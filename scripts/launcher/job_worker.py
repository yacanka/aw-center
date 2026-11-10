"""Optional durable job worker discovery for Django launch workflows."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .model import Project
from .process import non_notification_environment, start, starting_processes

WORKER_COMMAND_PATH = "jobs/management/commands/run_job_worker.py"
NOTIFICATION_COMMAND_PATH = (
    "compliance/management/commands/run_compdoc_notification_worker.py"
)
CLEANUP_COMMAND_PATH = "jobs/management/commands/run_job_cleanup_worker.py"


def start_job_workers(
    project: Project,
    extra_env: dict[str, str],
    *,
    include_doors_if_enabled: bool = False,
    heartbeat_dir: Path | None = None,
    protect_credentials: bool = False,
) -> list[subprocess.Popen]:
    """Start the repository's durable worker when its command is available."""

    with starting_processes() as workers:
        auxiliary_env = {**extra_env, "NUMARATOR_API_KEY": ""}
        if (project.backend / WORKER_COMMAND_PATH).is_file():
            command = [project.python, "manage.py", "run_job_worker", "--poll-interval", "1"]
            if include_doors_if_enabled:
                command.append("--include-doors-if-enabled")
            if heartbeat_dir is not None:
                command += ["--heartbeat-file", str(heartbeat_dir / "job")]
            worker_env = {**extra_env, **non_notification_environment()} if protect_credentials else extra_env
            workers.append(start(command, project.backend, extra_env=worker_env))
        if (project.backend / NOTIFICATION_COMMAND_PATH).is_file():
            command = [project.python, "manage.py", "run_compdoc_notification_worker"]
            if heartbeat_dir is not None:
                command += ["--heartbeat-file", str(heartbeat_dir / "notification")]
            workers.append(start(command, project.backend, extra_env=auxiliary_env))
        if (project.backend / CLEANUP_COMMAND_PATH).is_file():
            command = [
                project.python,
                "manage.py",
                "run_job_cleanup_worker",
                "--poll-interval",
                "300",
            ]
            if heartbeat_dir is not None:
                command += ["--heartbeat-file", str(heartbeat_dir / "cleanup")]
            cleanup_env = {**auxiliary_env, **non_notification_environment()} if protect_credentials else auxiliary_env
            workers.append(start(command, project.backend, extra_env=cleanup_env))
    return workers
