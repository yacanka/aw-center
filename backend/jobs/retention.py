"""Retention policy for private durable-job records and artifacts."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
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
    staging_files, orphan_outputs = cleanup_orphan_artifacts(now)
    return CleanupResult(
        expired_preview_count,
        deleted_objects,
        staging_files,
        orphan_outputs,
    )


def cleanup_orphan_artifacts(now=None):
    """Remove old unpublished staging and unreferenced final output files."""

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
    return staging_count, orphan_count


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
