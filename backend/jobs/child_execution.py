"""Model-backed execution inside a Django-initialized disposable process."""

from django.db import connections

from .contracts import JobCancelled, JobExecutionFailure, JobExecutionUncertain, JobLeaseLost
from .execution import bind_execution
from .models import Job


def execute_in_child(job_id, kind, resolve_executor, connection):
    """Run one allowlisted executor and send only a bounded result envelope."""

    connections.close_all()
    try:
        job = Job.objects.get(pk=job_id)
        with bind_execution(job):
            connection.send({"outcome": "ready"})
            executor = resolve_executor(kind)
            result = executor(job)
        connection.send(
            {
                "outcome": "succeeded",
                "result": {
                    "path": str(result.path),
                    "filename": result.filename,
                    "message": result.message,
                    "summary": result.summary,
                },
            }
        )
    except JobCancelled:
        connection.send({"outcome": "cancelled"})
    except JobLeaseLost:
        connection.send({"outcome": "lease_lost"})
    except JobExecutionUncertain as error:
        connection.send(
            {"outcome": "uncertain", "message": str(error), "code": error.code}
        )
    except JobExecutionFailure as error:
        connection.send(
            {
                "outcome": "failed",
                "message": str(error),
                "code": error.code,
                "retryable": error.retryable,
            }
        )
    except BaseException as error:
        connection.send({"outcome": "unhandled", "error_type": type(error).__name__})
    finally:
        connection.close()
        connections.close_all()
