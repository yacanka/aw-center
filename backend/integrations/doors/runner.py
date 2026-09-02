"""Host-local Windows runner for durable DOORS automation jobs."""

from __future__ import annotations

import hashlib
import hmac
import json
import multiprocessing
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import requests
from django.conf import settings
from django.utils.module_loading import import_string

from automations.catalog import DOORS_QUEUE, executor_metadata
from automations.identity import valid_runner_token
from awcenter.file_security import SAFE_NAME_PATTERN

RUNNER_API_PATH = "/internal/doors-runner/v1/"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
MAX_PROTOCOL_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024 * 1024


class RunnerConfigurationError(ValueError):
    """Reject a runner setup that would leave the local-host boundary."""


class RunnerProtocolError(RuntimeError):
    """Reject malformed or unsuccessful server protocol responses."""


class RunnerAuthenticationError(RunnerProtocolError):
    """Stop retrying when the runner credential is rejected."""


class RunnerClaimLost(RunnerProtocolError):
    """Stop publishing after the server has fenced the current execution."""


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    """Hold the local endpoint and credential used by one runner process."""

    base_url: str
    token: str
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise RunnerConfigurationError(
                "The DOORS runner URL must be a credential-free loopback origin."
            )
        try:
            parsed.port
        except ValueError as error:
            raise RunnerConfigurationError("The DOORS runner URL port is invalid.") from error
        if not valid_runner_token(self.token):
            raise RunnerConfigurationError("The DOORS runner token is invalid.")
        if not 0.1 <= float(self.connect_timeout_seconds) <= 30:
            raise RunnerConfigurationError("The runner connect timeout is invalid.")
        if not 1 <= float(self.read_timeout_seconds) <= 300:
            raise RunnerConfigurationError("The runner read timeout is invalid.")

    @property
    def origin(self) -> str:
        """Return the normalized loopback origin without a trailing slash."""

        return self.base_url.rstrip("/")

    def endpoint(self, relative_path: str) -> str:
        """Build only fixed runner API URLs on the configured loopback origin."""

        path = str(relative_path).lstrip("/")
        if not path or "?" in path or "#" in path or ".." in path:
            raise RunnerProtocolError("The runner endpoint path is invalid.")
        return f"{self.origin}{RUNNER_API_PATH}{path}"


@dataclass(frozen=True, slots=True)
class RunnerClaim:
    """Validated execution-scoped values returned by the Django data plane."""

    job_id: str
    kind: str
    executor: str
    execution_token: str
    timeout_seconds: int
    heartbeat_url: str
    heartbeat_interval_seconds: float
    input_name: str
    input_sha256: str
    input_url: str
    input_token: str
    input_maximum_bytes: int
    output_url: str
    output_token: str
    output_maximum_bytes: int


class DoorsRunnerClient:
    """Consume the loopback-only runner API without infrastructure credentials."""

    def __init__(self, config: RunnerConfig, session=None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "AW-Center-DOORS-Runner/1",
                "X-AWC-Runner-Token": config.token,
            }
        )

    @property
    def timeout(self) -> tuple[float, float]:
        return (
            self.config.connect_timeout_seconds,
            self.config.read_timeout_seconds,
        )

    def status(self) -> dict[str, object]:
        response = self.session.get(
            self.config.endpoint("status/"),
            allow_redirects=False,
            timeout=self.timeout,
        )
        return self._json_response(response, {200})

    def claim(self) -> RunnerClaim | None:
        response = self.session.post(
            self.config.endpoint("claims/"),
            json={},
            allow_redirects=False,
            timeout=self.timeout,
        )
        if response.status_code == 204:
            response.close()
            return None
        return validate_claim(self._json_response(response, {200}), self.config)

    def download_input(self, claim: RunnerClaim, target: Path) -> None:
        response = self.session.get(
            claim.input_url,
            headers=self._execution_headers(claim, claim.input_token),
            allow_redirects=False,
            stream=True,
            timeout=self.timeout,
        )
        self._require_status(response, {200})
        declared_digest = str(response.headers.get("X-AWC-Artifact-SHA256", "")).lower()
        digest = hashlib.sha256()
        total = 0
        try:
            with target.open("wb") as destination:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > claim.input_maximum_bytes:
                        raise RunnerProtocolError("The runner input exceeds its size limit.")
                    digest.update(chunk)
                    destination.write(chunk)
        finally:
            response.close()
        actual_digest = digest.hexdigest()
        if (
            total < 1
            or not hmac_digest_equal(actual_digest, claim.input_sha256)
            or not hmac_digest_equal(actual_digest, declared_digest)
        ):
            target.unlink(missing_ok=True)
            raise RunnerProtocolError("The runner input failed integrity verification.")

    def heartbeat(self, claim: RunnerClaim) -> bool:
        response = self.session.post(
            claim.heartbeat_url,
            json={"progress": 0},
            headers=self._execution_headers(claim),
            allow_redirects=False,
            timeout=self.timeout,
        )
        payload = self._json_response(response, {200}, claim_lost_statuses={409})
        return bool(payload.get("cancel_requested"))

    def complete_success(self, claim: RunnerClaim, output: Path, filename: str) -> None:
        size = output.stat().st_size
        if size < 1 or size > claim.output_maximum_bytes:
            raise RunnerProtocolError("The runner output exceeds its size limit.")
        digest = file_sha256(output)
        with output.open("rb") as stream:
            response = self.session.post(
                claim.output_url,
                data={
                    "status": "succeeded",
                    "sha256": digest,
                    "output_name": filename,
                },
                files={"file": (filename, stream, "application/json")},
                headers=self._execution_headers(claim, claim.output_token),
                allow_redirects=False,
                timeout=(
                    self.config.connect_timeout_seconds,
                    max(self.config.read_timeout_seconds, 120.0),
                ),
            )
        self._json_response(response, {200}, claim_lost_statuses={409})

    def complete_failure(self, claim: RunnerClaim, code: str, *, cancelled=False) -> None:
        response = self.session.post(
            claim.output_url,
            json={
                "status": "cancelled" if cancelled else "failed",
                "error_code": code,
            },
            headers=self._execution_headers(claim, claim.output_token),
            allow_redirects=False,
            timeout=self.timeout,
        )
        self._json_response(response, {200}, claim_lost_statuses={409})

    @staticmethod
    def _execution_headers(claim: RunnerClaim, artifact_token: str | None = None):
        headers = {"X-AWC-Execution-Token": claim.execution_token}
        if artifact_token:
            headers["X-AWC-Artifact-Token"] = artifact_token
        return headers

    def _json_response(
        self,
        response,
        expected_statuses: set[int],
        *,
        claim_lost_statuses: set[int] | None = None,
    ) -> dict[str, object]:
        self._require_status(response, expected_statuses, claim_lost_statuses)
        content = response.content
        response.close()
        if not content or len(content) > MAX_PROTOCOL_BYTES:
            raise RunnerProtocolError("The runner server returned an invalid response.")
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RunnerProtocolError("The runner server returned invalid JSON.") from error
        if not isinstance(payload, dict):
            raise RunnerProtocolError("The runner server response must be an object.")
        return payload

    @staticmethod
    def _require_status(response, expected_statuses, claim_lost_statuses=None) -> None:
        if response.status_code in expected_statuses:
            return
        status_code = response.status_code
        response.close()
        if status_code == 403:
            raise RunnerAuthenticationError("The runner credential was rejected.")
        if claim_lost_statuses and status_code in claim_lost_statuses:
            raise RunnerClaimLost("The runner execution claim is no longer active.")
        raise RunnerProtocolError(f"The runner server returned HTTP {status_code}.")


class DoorsRunner:
    """Poll, isolate, heartbeat, and publish one DOORS task at a time."""

    def __init__(self, client: DoorsRunnerClient, process_context=None) -> None:
        self.client = client
        self.process_context = process_context or multiprocessing.get_context("spawn")

    def poll_once(self) -> bool:
        claim = self.client.claim()
        if claim is None:
            return False
        self.execute_claim(claim)
        return True

    def execute_claim(self, claim: RunnerClaim) -> None:
        with tempfile.TemporaryDirectory(prefix="awcenter-doors-") as directory:
            temporary_root = Path(directory)
            input_path = temporary_root / claim.input_name
            output_path = temporary_root / "doors-result.json"
            self.client.download_input(claim, input_path)
            receiver, sender = self.process_context.Pipe(duplex=False)
            process = self.process_context.Process(
                target=execute_runner_task,
                args=(claim.kind, claim.executor, input_path, output_path, sender),
                name=f"doors-runner-{claim.job_id[:8]}",
                daemon=False,
            )
            try:
                process.start()
                sender.close()
                outcome = self._await_task(claim, process, receiver)
                if outcome is None:
                    return
                if outcome.get("outcome") != "succeeded":
                    self.client.complete_failure(
                        claim,
                        str(outcome.get("code", "DOORS_RUNNER_TASK_FAILED")),
                    )
                    return
                filename = validate_task_result(outcome.get("result"), output_path)
                self.client.complete_success(claim, output_path, filename)
            except KeyboardInterrupt:
                stop_process(process)
                try:
                    self.client.complete_failure(claim, "DOORS_RUNNER_SHUTDOWN")
                except (requests.RequestException, RunnerProtocolError):
                    pass
                raise
            finally:
                sender.close()
                receiver.close()
                stop_process(process)

    def _await_task(self, claim, process, receiver):
        deadline = time.monotonic() + claim.timeout_seconds
        next_heartbeat = time.monotonic() + claim.heartbeat_interval_seconds
        while True:
            remaining = min(deadline, next_heartbeat) - time.monotonic()
            if receiver.poll(max(0.0, min(0.25, remaining))):
                try:
                    return receiver.recv()
                except EOFError:
                    return {"outcome": "failed", "code": "DOORS_RUNNER_TASK_FAILED"}
            now = time.monotonic()
            if now >= deadline:
                stop_process(process)
                self.client.complete_failure(claim, "DOORS_RUNNER_TASK_TIMEOUT")
                return None
            if now >= next_heartbeat:
                if self.client.heartbeat(claim):
                    stop_process(process)
                    self.client.complete_failure(claim, "DOORS_RUNNER_SHUTDOWN", cancelled=True)
                    return None
                next_heartbeat = now + claim.heartbeat_interval_seconds
            if not process.is_alive():
                if receiver.poll(0.25):
                    continue
                return {"outcome": "failed", "code": "DOORS_RUNNER_TASK_FAILED"}


def validate_claim(payload: dict[str, object], config: RunnerConfig) -> RunnerClaim:
    """Validate every server-provided execution field before local dispatch."""

    if payload.get("schema_version") != 1 or payload.get("queue") != DOORS_QUEUE:
        raise RunnerProtocolError("The runner claim contract is unsupported.")
    contract = payload.get("contract")
    if contract != {
        "transport": "loopback_token",
        "database_access": "none",
        "cache_access": "none",
    }:
        raise RunnerProtocolError("The runner access contract is unsupported.")
    job = payload.get("job")
    if not isinstance(job, dict):
        raise RunnerProtocolError("The runner claim does not contain a job.")
    kind = str(job.get("kind", ""))
    metadata = executor_metadata(kind)
    executor = str(job.get("executor", ""))
    if (
        metadata is None
        or metadata.queue != DOORS_QUEUE
        or metadata.upload_policy is None
        or executor != metadata.dotted_path
    ):
        raise RunnerProtocolError("The runner claim executor is not allowlisted.")

    job_id = valid_uuid(job.get("id"))
    execution_token = valid_uuid(job.get("execution_token"))
    timeout_seconds = bounded_int(job.get("timeout_seconds"), 1, 600)
    heartbeat_interval = bounded_float(job.get("heartbeat_interval_seconds"), 0.5, 30.0)
    lease_seconds = bounded_int(job.get("lease_seconds"), 2, 3600)
    if timeout_seconds != metadata.timeout_seconds or heartbeat_interval * 2 > lease_seconds:
        raise RunnerProtocolError("The runner claim timing contract is invalid.")

    input_contract = job.get("input")
    output_contract = job.get("output")
    if not isinstance(input_contract, dict) or not isinstance(output_contract, dict):
        raise RunnerProtocolError("The runner artifact contract is invalid.")
    input_name = safe_basename(input_contract.get("name"))
    input_sha256 = valid_sha256(input_contract.get("sha256"))
    input_token = valid_capability(input_contract.get("artifact_token"))
    input_maximum = bounded_int(
        input_contract.get("maximum_bytes"), 1, metadata.upload_policy.maximum_bytes
    )
    extensions = input_contract.get("extensions")
    if (
        not isinstance(extensions, list)
        or Path(input_name).suffix.lower() not in metadata.upload_policy.extensions
        or Path(input_name).suffix.lower() not in {str(item) for item in extensions}
    ):
        raise RunnerProtocolError("The runner input type is invalid.")

    return RunnerClaim(
        job_id=job_id,
        kind=kind,
        executor=executor,
        execution_token=execution_token,
        timeout_seconds=timeout_seconds,
        heartbeat_url=validated_server_url(job.get("heartbeat_url"), config),
        heartbeat_interval_seconds=heartbeat_interval,
        input_name=input_name,
        input_sha256=input_sha256,
        input_url=validated_server_url(input_contract.get("download_url"), config),
        input_token=input_token,
        input_maximum_bytes=input_maximum,
        output_url=validated_server_url(output_contract.get("complete_url"), config),
        output_token=valid_capability(output_contract.get("artifact_token")),
        output_maximum_bytes=bounded_int(
            output_contract.get("maximum_bytes"), 1, MAX_OUTPUT_BYTES
        ),
    )


def execute_runner_task(
    kind: str,
    executor_path: str,
    input_path: Path,
    output_path: Path,
    sender,
) -> None:
    """Run one allowlisted callable in a disposable spawned Windows process."""

    try:
        metadata = executor_metadata(kind)
        if (
            metadata is None
            or metadata.queue != DOORS_QUEUE
            or metadata.dotted_path != executor_path
        ):
            raise RunnerProtocolError("The runner executor is not allowlisted.")
        executor = import_string(executor_path)
        result = executor(input_path, output_path)
        sender.send({"outcome": "succeeded", "result": result})
    except Exception as error:
        code = (
            "DOORS_RUNNER_INVALID_INPUT"
            if error.__class__.__name__ == "RunnerTaskPayloadError"
            else "DOORS_RUNNER_TASK_FAILED"
        )
        sender.send({"outcome": "failed", "code": code})
    finally:
        sender.close()


def validate_task_result(result, output_path: Path) -> str:
    if not isinstance(result, dict) or result.get("sha256_required") is not True:
        raise RunnerProtocolError("The DOORS executor returned an invalid result.")
    filename = safe_basename(result.get("filename"))
    if not output_path.is_file() or output_path.stat().st_size != result.get("bytes"):
        raise RunnerProtocolError("The DOORS executor output is incomplete.")
    return filename


def validated_server_url(value, config: RunnerConfig) -> str:
    path = str(value or "")
    if not path.startswith(RUNNER_API_PATH) or urlsplit(path).scheme or urlsplit(path).netloc:
        raise RunnerProtocolError("The runner server returned an invalid URL.")
    parsed = urlsplit(path)
    if parsed.query or parsed.fragment or ".." in parsed.path:
        raise RunnerProtocolError("The runner server returned an invalid URL.")
    return f"{config.origin}{parsed.path}"


def valid_uuid(value) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as error:
        raise RunnerProtocolError("The runner claim identifier is invalid.") from error


def valid_sha256(value) -> str:
    normalized = str(value or "").lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise RunnerProtocolError("The runner artifact digest is invalid.")
    return normalized


def valid_capability(value) -> str:
    normalized = str(value or "")
    if not TOKEN_PATTERN.fullmatch(normalized):
        raise RunnerProtocolError("The runner capability is invalid.")
    return normalized


def safe_basename(value) -> str:
    name = str(value or "")
    if not name or len(name) > 180 or Path(name).name != name or not SAFE_NAME_PATTERN.fullmatch(name):
        raise RunnerProtocolError("The runner artifact name is invalid.")
    return name


def bounded_int(value, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise RunnerProtocolError("The runner numeric contract is invalid.") from error
    if not minimum <= number <= maximum:
        raise RunnerProtocolError("The runner numeric contract is out of bounds.")
    return number


def bounded_float(value, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise RunnerProtocolError("The runner timing contract is invalid.") from error
    if not minimum <= number <= maximum:
        raise RunnerProtocolError("The runner timing contract is out of bounds.")
    return number


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hmac_digest_equal(first: str, second: str) -> bool:
    return bool(first and second and hmac.compare_digest(first, second))


def stop_process(process) -> None:
    if process is None:
        return
    try:
        alive = process.is_alive()
    except (AssertionError, ValueError):
        return
    if alive:
        process.join(timeout=0.5)
    if process.is_alive():
        process.terminate()
    process.join(timeout=5)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1)


def runner_token_from_windows_credential(target: str) -> str:
    """Read a Generic Credential scoped to the current Windows user."""

    if sys.platform != "win32" or not target:
        return ""
    try:
        import win32cred

        credential = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
        blob = credential.get("CredentialBlob", b"")
    except Exception:
        return ""
    if isinstance(blob, str):
        return blob if valid_runner_token(blob) else ""
    for encoding in ("utf-8", "utf-16-le"):
        try:
            candidate = bytes(blob).decode(encoding).rstrip("\x00")
        except (UnicodeError, ValueError):
            continue
        if valid_runner_token(candidate):
            return candidate
    return ""


def configured_runner_token() -> str:
    """Prefer the process secret, then the current user's Credential Manager."""

    token = str(settings.DOORS_RUNNER_TOKEN)
    if valid_runner_token(token):
        return token
    return runner_token_from_windows_credential(settings.DOORS_RUNNER_CREDENTIAL_TARGET)
