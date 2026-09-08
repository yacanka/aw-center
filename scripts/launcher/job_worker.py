"""Optional durable job worker discovery for Django launch workflows."""

from __future__ import annotations

import subprocess

from .model import Project
from .process import start

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
) -> list[subprocess.Popen]:
    """Start the repository's durable worker when its command is available."""

    workers = []
    auxiliary_env = {**extra_env, "NUMARATOR_API_KEY": ""}
    if (project.backend / WORKER_COMMAND_PATH).is_file():
        command = [project.python, "manage.py", "run_job_worker", "--poll-interval", "1"]
        if include_doors_if_enabled:
            command.append("--include-doors-if-enabled")
        workers.append(start(command, project.backend, extra_env=extra_env))
    if (project.backend / NOTIFICATION_COMMAND_PATH).is_file():
        command = [project.python, "manage.py", "run_compdoc_notification_worker"]
        workers.append(start(command, project.backend, extra_env=auxiliary_env))
    if (project.backend / CLEANUP_COMMAND_PATH).is_file():
        command = [
            project.python,
            "manage.py",
            "run_job_cleanup_worker",
            "--poll-interval",
            "300",
        ]
        workers.append(start(command, project.backend, extra_env=auxiliary_env))
    return workers
