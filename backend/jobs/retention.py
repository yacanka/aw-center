"""Retention policy for private durable-job records and artifacts."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Job, JobStatus


@dataclass(frozen=True)
class CleanupResult:
    expired_previews: int
    deleted_objects: int
    deleted_staging_files: int = 0
    deleted_orphan_outputs: int = 0


def cleanup_expired_jobs(days=None):
    """Delete expired previews and terminal jobs after validating retention."""

    retention_days = settings.JOB_ARTIFACT_RETENTION_DAYS if days is None else days
    if retention_days < 1:
        raise ValueError("Retention days must be at least one.")

    now = timezone.now()
    expired_previews = Job.objects.filter(
        status=JobStatus.AWAITING_CONFIRMATION,
        confirmation_expires_at__lt=now,
    )
    expired_preview_count = expired_previews.count()
    expired_previews.delete()

    cutoff = now - timedelta(days=retention_days)
    terminal_statuses = [
        JobStatus.CANCELLED,
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.RECONCILIATION_REQUIRED,
    ]
    deleted_objects, _ = Job.objects.filter(
        status__in=terminal_statuses, completed_at__lt=cutoff
    ).delete()
    if transaction.get_connection().in_atomic_block:
        # An outer rollback restores the job references. Do not classify their
        # files as orphans before that transaction has actually committed.
        transaction.on_commit(lambda: cleanup_orphan_artifacts(now))
        return CleanupResult(expired_preview_count, deleted_objects)
    staging_files, orphan_outputs = cleanup_orphan_artifacts(now)
    return CleanupResult(
        expired_preview_count,
        deleted_objects,
        staging_files,
        orphan_outputs,
    )


def cleanup_orphan_artifacts(now=None):
    """Remove old staging/output files; retry orphan input cleanup after commit."""

    current_time = now or timezone.now()
    grace_seconds = max(
        int(settings.JOB_EXECUTION_TIMEOUT_SECONDS),
        int(settings.JOB_LEASE_SECONDS),
        60,
    ) + 60
    cutoff = current_time.timestamp() - grace_seconds
    root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    staging_count = _delete_old_files(root / ".staging" / "jobs", cutoff)
    referenced = set(
        Job.objects.exclude(output_file="").values_list("output_file", flat=True)
    )
    orphan_count = 0
    jobs_root = root / "jobs"
    if jobs_root.is_dir():
        for path in jobs_root.glob("*/*/output*"):
            if not _old_regular_file(path, cutoff):
                continue
            relative = path.relative_to(root).as_posix()
            if relative in referenced:
                continue
            path.unlink(missing_ok=True)
            orphan_count += 1
    transaction.on_commit(lambda: _cleanup_orphan_inputs(current_time))
    return staging_count, orphan_count


def _cleanup_orphan_inputs(now):
    """Recover failed/missed post-commit deletes without touching live job files."""

    grace_seconds = max(
        int(settings.JOB_EXECUTION_TIMEOUT_SECONDS),
        int(settings.JOB_LEASE_SECONDS),
        60,
    ) + 60
    cutoff = now.timestamp() - grace_seconds
    root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    referenced = {
        name
        for files in Job.objects.values_list("input_file", "output_file")
        for name in files
        if name
    }
    jobs_root = root / "jobs"
    if jobs_root.is_symlink():
        return
    for path in jobs_root.glob("*/*/input*"):
        if path.parent.is_symlink() or path.parent.parent.is_symlink():
            continue
        if not _old_regular_file(path, cutoff):
            continue
        if path.relative_to(root).as_posix() not in referenced:
            path.unlink(missing_ok=True)


def _delete_old_files(directory, cutoff):
    if not directory.is_dir():
        return 0
    count = 0
    for path in directory.rglob("*.part"):
        if _old_regular_file(path, cutoff):
            path.unlink(missing_ok=True)
            count += 1
    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_dir() and not path.is_symlink():
            try:
                path.rmdir()
            except OSError:
                pass
    return count


def _old_regular_file(path, cutoff):
    try:
        return path.is_file() and not path.is_symlink() and path.stat().st_mtime < cutoff
    except OSError:
        return False
