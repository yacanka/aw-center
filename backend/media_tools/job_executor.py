import subprocess

from django.conf import settings

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobCancelled, JobExecutionFailure, JobExecutionResult
from jobs.worker import cancellation_requested, update_progress
from .services import build_ffmpeg_command, parse_parameters


def execute_media_conversion(job):
    """Convert one validated media artifact with cooperative cancellation."""

    parameters = parse_parameters(job.parameters)
    input_path = materialize_job_input(job)
    output_path = temporary_output(f".{parameters.output_extension}")
    result_ready = False
    try:
        update_progress(job.id, 15, "Input verified; starting FFmpeg.")
        run_cancellable_ffmpeg(job.id, input_path, output_path, parameters)
        update_progress(job.id, 90, "Conversion complete; storing output.")
        filename = f"converted.{parameters.output_extension}"
        result_ready = True
        return JobExecutionResult(output_path, filename, "Media conversion completed.")
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def run_cancellable_ffmpeg(job_id, input_path, output_path, parameters):
    """Run FFmpeg with timeout, lease heartbeats, and cancellation checks."""

    command = build_ffmpeg_command(input_path, output_path, parameters)
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline_seconds = int(getattr(settings, "JOB_EXECUTION_TIMEOUT_SECONDS", 900))
    elapsed = 0
    while process.poll() is None:
        wait_for_process(process)
        elapsed += heartbeat_seconds()
        if cancellation_requested(job_id):
            stop_process(process)
            raise JobCancelled()
        if elapsed >= deadline_seconds:
            stop_process(process)
            raise JobExecutionFailure("Media conversion timed out.", "JOB_TIMEOUT", True)
        update_progress(job_id, 25, "FFmpeg conversion is running.")
    ensure_success(process, output_path)


def wait_for_process(process):
    """Wait one bounded heartbeat interval for a child process."""

    try:
        process.communicate(timeout=heartbeat_seconds())
    except subprocess.TimeoutExpired:
        return


def stop_process(process):
    """Terminate and then force-kill a child process when required."""

    process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def ensure_success(process, output_path):
    """Reject failed or empty FFmpeg output without exposing stderr."""

    output_size = output_path.stat().st_size if output_path.exists() else 0
    if output_size > settings.JOB_MAX_OUTPUT_BYTES:
        output_path.unlink(missing_ok=True)
        raise JobExecutionFailure("Generated output exceeds the safety limit.", "JOB_OUTPUT_TOO_LARGE")
    if process.returncode != 0 or output_size == 0:
        output_path.unlink(missing_ok=True)
        raise JobExecutionFailure("Media conversion failed.", "MEDIA_CONVERSION_FAILED")


def heartbeat_seconds():
    """Return a bounded worker heartbeat interval."""

    return max(1, int(getattr(settings, "JOB_HEARTBEAT_SECONDS", 2)))
