"""Windows-worker adapter for the existing allowlisted DOORS task functions."""

from django.conf import settings

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult, JobExecutionUncertain

from integrations.doors import DoorsError

from . import runner_tasks


DOORS_TASKS = {
    "doors.run_dxl": runner_tasks.execute_dxl,
    "doors.update_object": runner_tasks.update_object,
    "doors.create_object": runner_tasks.create_object,
    "doors.link_requirements": runner_tasks.link_requirements,
}


def execute_doors_job(job):
    """Execute one catalogued DOORS job inside the supervised Windows worker."""

    if not settings.DOORS_ENABLED or settings.DOORS_EXECUTION_MODE != "worker":
        raise JobExecutionFailure(
            "DOORS worker execution is not configured.",
            "DOORS_NOT_CONFIGURED",
        )
    task = DOORS_TASKS.get(job.kind)
    if task is None:
        raise JobExecutionFailure("Unsupported DOORS job.", "DOORS_JOB_UNSUPPORTED")

    input_path = materialize_job_input(job)
    output_path = temporary_output(".json")
    result_ready = False
    try:
        try:
            metadata = task(input_path, output_path)
        except runner_tasks.RunnerTaskPayloadError as error:
            raise JobExecutionFailure(
                "DOORS automation input is invalid.",
                "DOORS_INPUT_INVALID",
            ) from error
        except DoorsError as error:
            if job.reconcile_on_lease_loss:
                raise JobExecutionUncertain() from error
            raise JobExecutionFailure(
                "The DOORS operation could not be completed.",
                "DOORS_OPERATION_FAILED",
                True,
            ) from error
        if metadata.get("sha256_required") is not True:
            raise JobExecutionFailure(
                "DOORS produced an invalid result.",
                "DOORS_OUTPUT_INVALID",
            )
        result_ready = True
        return JobExecutionResult(
            output_path,
            str(metadata.get("filename") or "doors-result.json"),
            "DOORS operation completed.",
        )
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)
