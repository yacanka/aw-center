"""Tests for the host-local DOORS runner client and protocol validation."""

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from integrations.doors.runner import (
    DoorsRunnerClient,
    RunnerConfig,
    RunnerConfigurationError,
    RunnerProtocolError,
    execute_runner_task,
    validate_claim,
)

RUNNER_TOKEN = "r" * 43


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8") if payload is not None else content
        self.headers = headers or {}
        self.closed = False

    def close(self):
        self.closed = True

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.responses = []
        self.calls = []

    def queue(self, response):
        self.responses.append(response)

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)


@override_settings(DOORS_RUNNER_MAX_INPUT_BYTES=1024 * 1024)
class DoorsRunnerProtocolTests(SimpleTestCase):
    def setUp(self):
        self.config = RunnerConfig("http://127.0.0.1:8765", RUNNER_TOKEN)

    def test_configuration_accepts_only_loopback_origin_and_strong_token(self):
        self.assertEqual(self.config.origin, "http://127.0.0.1:8765")
        for url in (
            "http://192.0.2.1:8765",
            "http://user:secret@127.0.0.1:8765",
            "http://127.0.0.1:8765/path",
            "file:///tmp/runner",
        ):
            with self.subTest(url=url), self.assertRaises(RunnerConfigurationError):
                RunnerConfig(url, RUNNER_TOKEN)
        with self.assertRaises(RunnerConfigurationError):
            RunnerConfig("http://127.0.0.1:8765", "too-short")

    def test_claim_uses_local_catalog_and_rejects_server_selected_origin(self):
        claim = validate_claim(self.claim_payload(), self.config)

        self.assertEqual(claim.kind, "doors.run_dxl")
        self.assertEqual(
            claim.input_url,
            f"{self.config.origin}/internal/doors-runner/v1/jobs/{claim.job_id}/input/",
        )

        malicious = self.claim_payload()
        malicious["job"]["input"]["download_url"] = "https://example.test/input"
        with self.assertRaises(RunnerProtocolError):
            validate_claim(malicious, self.config)

        unsupported = self.claim_payload()
        unsupported["job"]["executor"] = "builtins.eval"
        with self.assertRaises(RunnerProtocolError):
            validate_claim(unsupported, self.config)

        unsupported_contract = self.claim_payload()
        unsupported_contract["contract"]["database_access"] = "direct"
        with self.assertRaises(RunnerProtocolError):
            validate_claim(unsupported_contract, self.config)

    def test_child_process_rechecks_executor_allowlist(self):
        sender = RecordingSender()

        execute_runner_task(
            "doors.run_dxl",
            "builtins.eval",
            Path("unused-input.json"),
            Path("unused-output.json"),
            sender,
        )

        self.assertEqual(
            sender.messages,
            [{"outcome": "failed", "code": "DOORS_RUNNER_TASK_FAILED"}],
        )
        self.assertTrue(sender.closed)

    def test_client_authenticates_and_verifies_download_digest(self):
        content = b'{"operation":"check_module"}'
        digest = hashlib.sha256(content).hexdigest()
        payload = self.claim_payload(input_sha256=digest)
        session = FakeSession()
        session.queue(FakeResponse(payload=payload))
        session.queue(
            FakeResponse(content=content, headers={"X-AWC-Artifact-SHA256": digest})
        )
        client = DoorsRunnerClient(self.config, session=session)

        claim = client.claim()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "input.json"
            client.download_input(claim, target)
            self.assertEqual(target.read_bytes(), content)

        self.assertEqual(session.headers["X-AWC-Runner-Token"], RUNNER_TOKEN)
        self.assertEqual(session.calls[0][1], self.config.endpoint("claims/"))
        self.assertEqual(
            session.calls[1][2]["headers"]["X-AWC-Artifact-Token"],
            claim.input_token,
        )

    def test_client_removes_corrupt_download(self):
        content = b"corrupt"
        payload = self.claim_payload(input_sha256="0" * 64)
        session = FakeSession()
        session.queue(FakeResponse(payload=payload))
        session.queue(
            FakeResponse(
                content=content,
                headers={"X-AWC-Artifact-SHA256": hashlib.sha256(content).hexdigest()},
            )
        )
        client = DoorsRunnerClient(self.config, session=session)
        claim = client.claim()

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "input.json"
            with self.assertRaises(RunnerProtocolError):
                client.download_input(claim, target)
            self.assertFalse(target.exists())

    def claim_payload(self, *, input_sha256="0" * 64):
        job_id = str(uuid4())
        base = f"/internal/doors-runner/v1/jobs/{job_id}"
        return {
            "schema_version": 1,
            "queue": "doors",
            "job": {
                "id": job_id,
                "kind": "doors.run_dxl",
                "executor": "integrations.doors.runner_tasks.execute_dxl",
                "execution_token": str(uuid4()),
                "timeout_seconds": 120,
                "heartbeat_url": f"{base}/heartbeat/",
                "heartbeat_interval_seconds": 5,
                "lease_seconds": 60,
                "lease_expires_at": "2030-01-01T00:00:00+00:00",
                "input": {
                    "name": "doors-operation.json",
                    "sha256": input_sha256,
                    "download_url": f"{base}/input/",
                    "artifact_token": "i" * 43,
                    "extensions": [".json"],
                    "maximum_bytes": 1024 * 1024,
                },
                "output": {
                    "complete_url": f"{base}/complete/",
                    "artifact_token": "o" * 43,
                    "maximum_bytes": 10 * 1024 * 1024,
                },
            },
            "contract": {
                "transport": "loopback_token",
                "database_access": "none",
                "cache_access": "none",
            },
        }


class RecordingSender:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, payload):
        self.messages.append(payload)

    def close(self):
        self.closed = True
