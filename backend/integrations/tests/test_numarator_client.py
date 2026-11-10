"""Contract tests for the bounded Numarator client."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

from django.test import SimpleTestCase, override_settings

from integrations.numarator.client import (
    NumaratorClient, NumaratorConflictError, NumaratorRejectedError,
    NumaratorTemporaryError,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=201, headers=None):
        self.body = json.dumps(payload).encode("utf-8")
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.calls = []
        self.verify = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response

    def close(self):
        pass


@override_settings(
    DEBUG=False,
    NUMARATOR_ENABLED=True,
    NUMARATOR_BASE_URL="https://numarator.example.test",
    NUMARATOR_API_KEY="dnk_secret",
    NUMARATOR_CREDENTIAL_ID="test-v1",
    NUMARATOR_VERIFY_SSL=True,
    NUMARATOR_CONNECT_TIMEOUT_SECONDS=3,
    NUMARATOR_READ_TIMEOUT_SECONDS=10,
    NUMARATOR_MAX_RESPONSE_BYTES=1024,
)
class NumaratorClientTests(SimpleTestCase):
    def test_custom_ca_is_not_replaced_by_process_wide_requests_bundle(self):
        with TemporaryDirectory() as directory:
            certificate = Path(directory) / "numarator.pem"
            certificate.touch()
            response = FakeResponse({"success": True, "data": {
                "code": "COVER_PAGE", "required_context": [],
            }})
            with override_settings(NUMARATOR_CERTIFICATE_FILE=certificate), patch.dict(
                os.environ, {"REQUESTS_CA_BUNDLE": "/different-service-ca.pem"},
            ), requests.Session() as session, patch.object(session, "send", return_value=response) as send:
                result = NumaratorClient(session=session).describe_format("COVER_PAGE")
            self.assertEqual(result["fields"], [])
            self.assertEqual(send.call_args.kwargs["verify"], str(certificate))

    def test_rejections_identify_configuration_problem_without_upstream_body(self):
        for status, expected in (
            (401, "API key"), (403, "permission"), (404, "endpoint"),
        ):
            with self.subTest(status=status):
                response = FakeResponse({"detail": "private upstream data"}, status_code=status)
                with self.assertRaises(NumaratorRejectedError) as raised:
                    NumaratorClient(session=FakeSession(response)).describe_format("COVER_PAGE")
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("private upstream data", str(raised.exception))
                self.assertTrue(response.closed)

    def test_tls_failure_explains_certificate_check_without_raw_exception(self):
        with requests.Session() as session, patch.object(
            session, "request", side_effect=requests.exceptions.SSLError("private host and path"),
        ):
            with self.assertRaises(NumaratorTemporaryError) as raised:
                NumaratorClient(session=session).describe_format("COVER_PAGE")
        self.assertIn("TLS", str(raised.exception))
        self.assertNotIn("private host", str(raised.exception))

    def test_generate_uses_private_endpoint_and_idempotency_header(self):
        response = FakeResponse(
            {
                "success": True,
                "data": {
                    "id": 7,
                    "document_number": "CP-0007",
                    "format_code": "COVER_PAGE",
                    "status": "active",
                },
            },
            headers={"X-Request-ID": "remote-request"},
        )
        session = FakeSession(response)
        client = NumaratorClient(session=session)

        result = client.generate_number(
            format_code="COVER_PAGE",
            context_data={"project": "ozgur"},
            metadata={"source": "aw-center"},
            external_reference="allocation-id",
            idempotency_key="awc-cover-page:allocation-id",
        )

        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://numarator.example.test/api/private/v1/numbers/")
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "awc-cover-page:allocation-id")
        self.assertEqual(result.number, "CP-0007")
        self.assertEqual(result.request_id, "remote-request")
        self.assertNotIn("dnk_secret", str(session.calls))
        self.assertTrue(response.closed)

    @override_settings(NUMARATOR_MAX_RESPONSE_BYTES=5)
    def test_oversized_response_is_rejected_and_closed(self):
        response = FakeResponse({"success": True, "data": {}})
        session = FakeSession(response)

        with self.assertRaises(NumaratorConflictError):
            NumaratorClient(session=session).mark_used(1)

        self.assertTrue(response.closed)

    def test_format_contract_exposes_only_input_metadata(self):
        response = FakeResponse({"success": True, "data": {
            "code": "COVER_PAGE", "internal": "not exposed",
            "required_context": [{"key": "department", "required": False, "default": "GEN", "max_length": 10}],
        }})
        session = FakeSession(response)
        result = NumaratorClient(session=session).describe_format("COVER_PAGE")
        self.assertEqual(result, {"code": "COVER_PAGE", "fields": [
            {"key": "department", "required": False, "default": "GEN", "max_length": 10},
        ]})
        self.assertEqual(session.calls[0][0:2], ("GET", "https://numarator.example.test/api/private/v1/formats/COVER_PAGE/"))
        self.assertIsNone(session.calls[0][2]["json"])
        self.assertTrue(response.closed)

    def test_format_contract_rejects_missing_fields_instead_of_assuming_no_input(self):
        response = FakeResponse({"success": True, "data": {"code": "COVER_PAGE"}})
        with self.assertRaises(NumaratorConflictError):
            NumaratorClient(session=FakeSession(response)).describe_format("COVER_PAGE")
