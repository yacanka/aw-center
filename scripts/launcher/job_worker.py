"""Optional durable job worker discovery for Django launch workflows."""

from __future__ import annotations

import subprocess

from .model import Project
from .process import start

WORKER_COMMAND_PATH = "jobs/management/commands/run_job_worker.py"


def start_job_workers(
    project: Project, extra_env: dict[str, str]
) -> list[subprocess.Popen]:
    """Start the repository's durable worker when its command is available."""

    if not (project.backend / WORKER_COMMAND_PATH).is_file():
        return []
    command = [project.python, "manage.py", "run_job_worker", "--poll-interval", "1"]
    return [start(command, project.backend, extra_env=extra_env)]
