import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .contracts import JobExecutionFailure
from .models import job_output_path


SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]{1,16}$")


@dataclass(frozen=True)
class StagedJobArtifact:
    """Describe a hashed private artifact awaiting a fenced atomic publish."""

    storage: object
    staging_path: Path
    final_path: Path
    final_name: str
    digest: str


def materialize_job_input(job):
    """Copy and integrity-check a stored job input into a temporary file."""

    suffix = Path(job.input_name).suffix.lower()
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    digest = hashlib.sha256()
    with job.input_file.open("rb") as source, temporary:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            temporary.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != job.input_sha256:
        Path(temporary.name).unlink(missing_ok=True)
        raise JobExecutionFailure("Stored input failed integrity verification.", "JOB_INPUT_CORRUPT")
    return Path(temporary.name)


def temporary_output(suffix):
    """Reserve an isolated output path with a controlled suffix."""

    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temporary.close()
    return Path(temporary.name)


def stage_job_output(job, filename, source) -> StagedJobArtifact:
    """Write a result into an execution-scoped staging file and hash it."""

    output_name = str(filename or "").strip()
    suffix = Path(output_name).suffix.lower()
    if (
        not output_name
        or len(output_name) > 180
        or Path(output_name).name != output_name
        or (suffix and not SAFE_SUFFIX.fullmatch(suffix))
        or job.execution_token is None
    ):
        raise JobExecutionFailure(
            "The executor returned an invalid output name.",
            "JOB_OUTPUT_NAME_INVALID",
        )
    storage = job.output_file.storage
    root = Path(storage.location).resolve()
    final_name = job_output_path(job, output_name)
    final_path = _safe_storage_path(storage, root, final_name)
    staging_path = _safe_storage_path(
        storage,
        root,
        (
            f".staging/jobs/{job.owner_id}/{job.id}/"
            f"{job.execution_token.hex}{suffix or '.bin'}.part"
        ),
    )
    staging_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256()
    descriptor = os.open(staging_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            for chunk in _source_chunks(source):
                destination.write(chunk)
                digest.update(chunk)
            destination.flush()
            os.fsync(destination.fileno())
    except Exception:
        staging_path.unlink(missing_ok=True)
        raise
    return StagedJobArtifact(
        storage=storage,
        staging_path=staging_path,
        final_path=final_path,
        final_name=final_name,
        digest=digest.hexdigest(),
    )


def publish_staged_job_output(artifact: StagedJobArtifact) -> None:
    """Atomically make a fully written staged artifact the private final file."""

    artifact.final_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.replace(artifact.staging_path, artifact.final_path)
    _fsync_directory(artifact.final_path.parent)


def discard_staged_job_output(artifact: StagedJobArtifact | None, *, published=False):
    """Remove unpublished staging or rollback an unreferenced final artifact."""

    if artifact is None:
        return
    target = artifact.final_path if published else artifact.staging_path
    target.unlink(missing_ok=True)


def _source_chunks(source):
    if hasattr(source, "seek"):
        source.seek(0)
    if hasattr(source, "chunks"):
        yield from source.chunks()
        return
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            return
        yield chunk


def _safe_storage_path(storage, root, name):
    path = Path(storage.path(name)).resolve()
    if not path.is_relative_to(root):
        raise JobExecutionFailure(
            "The artifact storage path is invalid.",
            "JOB_OUTPUT_PATH_INVALID",
        )
    return path


def _fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
