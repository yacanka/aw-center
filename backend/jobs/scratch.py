"""Parent-owned scratch directories for disposable job executor processes."""

import logging
import os
from pathlib import Path
import shutil
import tempfile
from uuid import UUID

logger = logging.getLogger(__name__)


def create_execution_scratch(job):
    """Reserve a private directory unique to an already claimed execution."""

    from django.conf import settings

    root = Path(settings.PRIVATE_MEDIA_ROOT).resolve() / ".scratch" / "jobs"
    directory = root / str(job.owner_id) / str(job.id) / job.execution_token.hex
    if _has_symlink_ancestor(directory, root):
        raise ValueError("The execution scratch location is invalid.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    return directory


def configure_execution_scratch(directory):
    """Confine Python/library and descendant temporary files to the child scratch."""

    path = str(directory)
    if not Path(path).is_dir():
        raise ValueError("The execution scratch directory is unavailable.")
    # This runs only in the disposable child, before Django or feature imports.
    # Reset the cached tempfile location as fork may inherit the parent's value.
    tempfile.tempdir = path
    for name in ("TMPDIR", "TEMP", "TMP"):
        os.environ[name] = path


def remove_execution_scratch(directory):
    """Best-effort removal after process containment confirms no remaining writers."""

    if directory is None:
        return False
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        return True
    except OSError as error:
        # Windows sharing locks can outlive process termination briefly. Leave
        # these files for retention instead of failing a completed operation.
        logger.warning(
            "Execution scratch cleanup deferred",
            extra={"error_type": type(error).__name__},
        )
        return False
    return True


def cleanup_orphan_execution_scratch(private_root, cutoff):
    """Remove only old owned directories no current execution can still use."""

    from .models import Job, JobStatus

    root = private_root / ".scratch" / "jobs"
    if root.parent.is_symlink() or root.is_symlink() or not root.is_dir():
        return
    for directory in root.glob("*/*/*"):
        identity = _old_scratch_identity(directory, root, cutoff)
        if identity is None:
            continue
        owner_id, job_id, token = identity
        # Even an expired claim may still have a running child awaiting parent
        # containment/recovery. Only a released or replaced token is an orphan.
        active = Job.objects.filter(
            pk=job_id,
            owner_id=owner_id,
            execution_token=token,
            status__in=(JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED),
        ).exists()
        if not active:
            remove_execution_scratch(directory)


def _old_scratch_identity(directory, root, cutoff):
    if _has_symlink_ancestor(directory, root):
        return None
    try:
        if not directory.is_dir() or directory.stat().st_mtime >= cutoff:
            return None
        owner = directory.parent.parent.name
        job = directory.parent.name
        token = directory.name
        if str(int(owner)) != owner or int(owner) < 1:
            return None
        if str(UUID(job)) != job or UUID(token).hex != token:
            return None
        return int(owner), UUID(job), UUID(token)
    except (OSError, ValueError):
        return None


def _has_symlink_ancestor(directory, root):
    return any(path.is_symlink() for path in (
        root.parent, root, directory.parent.parent, directory.parent, directory,
    ))
