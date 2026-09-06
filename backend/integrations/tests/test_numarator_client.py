"""Contract tests for the bounded Numarator client."""

import json

from django.test import SimpleTestCase, override_settings

from integrations.numarator.client import NumaratorClient, NumaratorConflictError


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
