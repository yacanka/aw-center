import hashlib
import tempfile
from pathlib import Path

from .contracts import JobExecutionFailure


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
