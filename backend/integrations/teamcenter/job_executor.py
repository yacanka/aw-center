"""Durable Teamcenter external-write executor."""

import json

from django.conf import settings

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import (
    JobExecutionFailure,
    JobExecutionResult,
    JobExecutionUncertain,
)
from jobs.execution import update_progress

from integrations.teamcenter.exceptions import (
    TeamcenterAuthenticationError,
    TeamcenterConfigurationError,
    TeamcenterConnectionError,
    TeamcenterProtocolError,
    TeamcenterServiceError,
)
from .operations import build_property_updates
from .serializers import SetPropertiesSerializer
from .services import execute_with_client


def execute_set_properties(job):
    """Apply one validated batch and produce a content-free private receipt."""

    input_path = materialize_job_input(job)
    output_path = temporary_output(".json")
    result_ready = False
    try:
        if not settings.TEAMCENTER_ENABLED:
            raise JobExecutionFailure(
                "Teamcenter is not enabled.",
                "TEAMCENTER_NOT_CONFIGURED",
            )
        payload = load_payload(input_path)
        serializer = SetPropertiesSerializer(data=payload)
        if not serializer.is_valid():
            raise JobExecutionFailure(
                "Teamcenter update input is invalid.",
                "TEAMCENTER_INPUT_INVALID",
            )
        updates = build_property_updates(serializer.validated_data["updates"])
        update_progress(job.id, 20, "Teamcenter update input verified.")
        try:
            execute_with_client(lambda client: client.set_properties(updates))
        except (TeamcenterConnectionError, TeamcenterProtocolError) as error:
            raise JobExecutionUncertain() from error
        except (TeamcenterConfigurationError, TeamcenterAuthenticationError) as error:
            raise JobExecutionFailure(
                "Teamcenter authentication or configuration failed.",
                "TEAMCENTER_NOT_CONFIGURED",
            ) from error
        except TeamcenterServiceError as error:
            raise JobExecutionFailure(
                "Teamcenter rejected the property update.",
                "TEAMCENTER_WRITE_REJECTED",
            ) from error
        receipt = {
            "status": "completed",
            "updated_objects": len(serializer.validated_data["updates"]),
        }
        output_path.write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        result_ready = True
        return JobExecutionResult(
            output_path,
            "teamcenter-update-receipt.json",
            "Teamcenter property update completed.",
            receipt,
        )
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def load_payload(path):
    """Load one bounded JSON object from a verified private artifact."""

    if path.stat().st_size > 1024 * 1024:
        raise JobExecutionFailure(
            "Teamcenter update input is too large.",
            "TEAMCENTER_INPUT_INVALID",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JobExecutionFailure(
            "Teamcenter update input is invalid.",
            "TEAMCENTER_INPUT_INVALID",
        ) from error
    if not isinstance(payload, dict):
        raise JobExecutionFailure(
            "Teamcenter update input is invalid.",
            "TEAMCENTER_INPUT_INVALID",
        )
    return payload
