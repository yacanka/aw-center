"""Windows-worker adapter for the existing allowlisted DOORS task functions."""

from django.conf import settings

from jobs.artifacts import materialize_job_input, remove_temporary_artifact, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult, JobExecutionUncertain

from integrations.doors import DoorsError
from .exceptions import DoorsConnectionError, DoorsConfigurationError, DoorsOperationError

from . import worker_tasks


DOORS_TASKS = {
    "doors.run_dxl": worker_tasks.execute_dxl,
    "doors.update_object": worker_tasks.update_object,
    "doors.create_object": worker_tasks.create_object,
    "doors.link_requirements": worker_tasks.link_requirements,
}


def execute_doors_job(job):
    """Execute one catalogued DOORS job inside the supervised Windows worker."""

    if not settings.DOORS_ENABLED:
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
        except worker_tasks.WorkerTaskPayloadError as error:
            raise JobExecutionFailure(
                "DOORS automation input is invalid.",
                "DOORS_INPUT_INVALID",
            ) from error
        except DoorsConnectionError as error:
            # Connection/probe failures happen before any business DXL is sent.
            code = error.code if error.code in CONNECTION_FAILURES else "DOORS_CONNECTION_FAILED"
            raise JobExecutionFailure(
                CONNECTION_FAILURES[code], code, not isinstance(error, DoorsConfigurationError)
            ) from None
        except DoorsError as error:
            rejected_before_write = isinstance(error, DoorsOperationError) and error.code in PRE_WRITE_ERRORS
            if job.reconcile_on_lease_loss and not rejected_before_write:
                raise JobExecutionUncertain() from error
            # Upstream detail may contain module paths or data. Expose only a
            # code produced by our fixed builders, never arbitrary DXL text.
            code = error.code
            if isinstance(error, DoorsOperationError):
                code = SAFE_OPERATION_CODES.get(code, "DOORS_OPERATION_FAILED")
            message = OPERATION_FAILURE_MESSAGES.get(
                code,
                "The DOORS operation could not be completed. Check the DOORS client and module access.",
            )
            if code == "DOORS_MODULE_ALREADY_OPEN" and job.kind == "doors.link_requirements":
                message = "Close the source module in the desktop client before submitting a link operation."
            raise JobExecutionFailure(
                message,
                code,
                True,
            ) from None
        if metadata.get("sha256_required") is not True:
            raise JobExecutionFailure(
                "DOORS produced an invalid result.",
                "DOORS_OUTPUT_INVALID",
            )
        result_ready = True
        return JobExecutionResult(
            output_path,
            str(metadata.get("filename") or "doors-result.json"),
            metadata.get("message") or "DOORS operation completed.",
        )
    finally:
        remove_temporary_artifact(input_path)
        if not result_ready:
            remove_temporary_artifact(output_path)


SAFE_OPERATION_CODES = {
    code: "DOORS_" + code for code in (
        "OPEN_MODULE", "OPEN_MODULE_EDIT", "OPEN_REFERENCE_MODULE", "OPEN_TARGET_MODULE",
        "OBJECT_NOT_FOUND", "ATTRIBUTE_NOT_FOUND", "ATTRIBUTE_AMBIGUOUS", "MODULE_ALREADY_OPEN",
        "READ_ATTRIBUTE", "SET_ATTRIBUTE", "SAVE_MODULE", "CREATE_OBJECT", "AMBIGUOUS_TARGET",
        "BASE_OBJECT_NOT_FOUND", "REFERENCE_OBJECT_LIMIT", "LINK_CANDIDATE_LIMIT", "TARGET_OBJECT_LIMIT",
    )
}

OPERATION_FAILURE_MESSAGES = {
    "DOORS_OPEN_MODULE": "Module not found or no read access. Check the module path and read permission.",
    "DOORS_OPEN_MODULE_EDIT": "The module could not be opened for editing. Check modify permission and module locks.",
    "DOORS_MODULE_ALREADY_OPEN": "The module is already open in edit or shared mode. Save and close it before submitting a write.",
    "DOORS_OBJECT_NOT_FOUND": "The requested object was not found in the module.",
    "DOORS_BASE_OBJECT_NOT_FOUND": "The relative object was not found in the module.",
    "DOORS_ATTRIBUTE_NOT_FOUND": "The requested attribute was not found in the module.",
}

PRE_WRITE_ERRORS = frozenset({
    "MODULE_ALREADY_OPEN", "OPEN_MODULE_EDIT", "OPEN_REFERENCE_MODULE", "OPEN_TARGET_MODULE",
    "OBJECT_NOT_FOUND", "BASE_OBJECT_NOT_FOUND", "ATTRIBUTE_NOT_FOUND", "AMBIGUOUS_TARGET",
    "REFERENCE_OBJECT_LIMIT", "LINK_CANDIDATE_LIMIT", "TARGET_OBJECT_LIMIT", "LINK_KEY_LIMIT",
})

CONNECTION_FAILURES = {
    "DOORS_COM_DEPENDENCY_UNAVAILABLE": (
        "The Windows COM dependency is unavailable. Reinstall the locked Windows dependencies."
    ),
    "DOORS_CONFIG_INVALID": "DOORS settings are invalid. Check the client configuration.",
    "DOORS_CONNECTION_FAILED": "Cannot connect to DOORS. Check the Windows desktop session, client installation and login.",
    "DOORS_PLATFORM_UNSUPPORTED": "DOORS requires a worker running in an interactive Windows user session.",
    "DOORS_DEPENDENCY_UNAVAILABLE": "DOORS Windows dependencies could not be loaded. Repair pywin32 in the worker's Python environment and restart AW Center.",
    "DOORS_COM_INITIALIZATION_FAILED": "Windows COM could not be initialized. Restart AW Center in the DOORS user's desktop session.",
    "DOORS_PROCESS_INSPECTION_FAILED": "Windows process inspection failed. Check the worker's desktop session and process query permissions.",
    "DOORS_CLIENT_NOT_RUNNING": "No DOORS client is running and automatic startup is disabled. Open DOORS or enable DOORS_AUTO_START_CLIENT.",
    "DOORS_CLIENT_START_FAILED": "DOORS could not be started. Check the executable's permissions or open the client manually.",
    "DOORS_EXECUTABLE_UNAVAILABLE": "DOORS executable was not found. Check DOORS_EXECUTABLE and DOORS_OLE_PROG_ID.",
    "DOORS_PROCESS_INSPECTOR_UNAVAILABLE": (
        "The Windows WMI dependency is unavailable. Reinstall the locked Windows dependencies."
    ),
    "DOORS_STARTUP_TIMEOUT": "DOORS did not become ready. Check login, database, license and open dialogs.",
    "DOORS_MULTIPLE_CLIENTS": "Multiple DOORS clients are open. Keep one client in the worker's Windows session.",
}
