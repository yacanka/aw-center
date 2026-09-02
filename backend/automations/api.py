"""HTTP endpoints for the host-local DOORS runner protocol."""

from django.http import FileResponse
from django.urls import reverse
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .runner_protocol import (
    RunnerRequestInvalid,
    runner_poll_interval,
    claim_doors_job,
    complete_doors_job,
    heartbeat_doors_job,
    maximum_output_bytes,
    open_input_artifact,
)
from .identity import authenticate_runner


class NoBrowserAuthentication(BaseAuthentication):
    """Make explicit that runner endpoints never authenticate browser principals."""

    def authenticate(self, request):
        return None


@api_view(["GET"])
@authentication_classes([NoBrowserAuthentication])
@permission_classes([AllowAny])
def runner_status_view(request):
    """Confirm the local data-plane contract to an authenticated runner."""

    authenticate_runner_request(request)
    return no_store(
        Response(
            {
                "enabled": True,
                "queue": "doors",
                "transport": "loopback_token",
                "database_access": "none",
                "cache_access": "none",
                "poll_interval_seconds": runner_poll_interval(),
            }
        )
    )


@api_view(["POST"])
@authentication_classes([NoBrowserAuthentication])
@permission_classes([AllowAny])
def claim(request):
    """Lease one allowlisted DOORS job without accepting user credentials."""

    identity = authenticate_runner_request(request)
    claimed = claim_doors_job(identity)
    if claimed is None:
        return no_store(Response(status=status.HTTP_204_NO_CONTENT))
    input_url = reverse("doors_runner_input", kwargs={"job_id": claimed.job_id})
    heartbeat_url = reverse(
        "doors_runner_heartbeat", kwargs={"job_id": claimed.job_id}
    )
    complete_url = reverse(
        "doors_runner_complete", kwargs={"job_id": claimed.job_id}
    )
    policy = claimed.metadata.upload_policy
    response = Response(
        {
            "schema_version": 1,
            "queue": "doors",
            "job": {
                "id": str(claimed.job_id),
                "kind": claimed.kind,
                "executor": claimed.metadata.dotted_path,
                "execution_token": str(claimed.execution_token),
                "timeout_seconds": claimed.metadata.timeout_seconds,
                "heartbeat_url": heartbeat_url,
                "heartbeat_interval_seconds": claimed.heartbeat_interval_seconds,
                "lease_seconds": claimed.lease_seconds,
                "lease_expires_at": claimed.lease_expires_at.isoformat(),
                "input": {
                    "name": claimed.input_name,
                    "sha256": claimed.input_sha256,
                    "download_url": input_url,
                    "artifact_token": claimed.input_token,
                    "extensions": sorted(policy.extensions) if policy else [],
                    "maximum_bytes": policy.maximum_bytes if policy else 0,
                },
                "output": {
                    "complete_url": complete_url,
                    "artifact_token": claimed.output_token,
                    "maximum_bytes": maximum_output_bytes(),
                },
            },
            "contract": {
                "transport": "loopback_token",
                "database_access": "none",
                "cache_access": "none",
            },
        }
    )
    return no_store(response)


@api_view(["GET"])
@authentication_classes([NoBrowserAuthentication])
@permission_classes([AllowAny])
def download_input(request, job_id):
    """Stream one SHA-verified input after atomically consuming its capability."""

    identity = authenticate_runner_request(request)
    execution_token = required_header(request, "X-AWC-Execution-Token")
    artifact_token = required_header(request, "X-AWC-Artifact-Token")
    artifact, filename, digest = open_input_artifact(
        identity, job_id, execution_token, artifact_token
    )
    response = FileResponse(artifact, as_attachment=True, filename=filename)
    response["X-AWC-Artifact-SHA256"] = digest
    return no_store(response)


@api_view(["POST"])
@authentication_classes([NoBrowserAuthentication])
@permission_classes([AllowAny])
def heartbeat(request, job_id):
    """Renew one claim and return cooperative cancellation intent."""

    identity = authenticate_runner_request(request)
    execution_token = required_header(request, "X-AWC-Execution-Token")
    payload = request.data if isinstance(request.data, dict) else {}
    result = heartbeat_doors_job(
        identity, job_id, execution_token, payload.get("progress")
    )
    return no_store(Response(result))


@api_view(["POST"])
@authentication_classes([NoBrowserAuthentication])
@permission_classes([AllowAny])
def complete(request, job_id):
    """Publish one fenced success/failure using the output transfer capability."""

    identity = authenticate_runner_request(request)
    execution_token = required_header(request, "X-AWC-Execution-Token")
    artifact_token = required_header(request, "X-AWC-Artifact-Token")
    completion_status = str(request.data.get("status", ""))
    terminal_status = complete_doors_job(
        identity,
        job_id,
        execution_token,
        artifact_token,
        completion_status,
        uploaded_file=request.FILES.get("file"),
        declared_sha256=str(request.data.get("sha256", "")),
        output_name=str(request.data.get("output_name", "")),
        failure_code=str(request.data.get("error_code", "")),
    )
    return no_store(Response({"job_id": str(job_id), "status": terminal_status}))


def authenticate_runner_request(request):
    """Reject query credentials before applying runner authentication."""

    if request.query_params:
        raise RunnerRequestInvalid()
    return authenticate_runner(request)


def required_header(request, name):
    value = str(request.headers.get(name, "")).strip()
    if not value:
        raise RunnerRequestInvalid()
    return value


def no_store(response):
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response
