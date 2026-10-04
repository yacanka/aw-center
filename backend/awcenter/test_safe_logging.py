"""Regression tests for safe API and worker error diagnostics."""

import json
import logging
from types import SimpleNamespace

from django.test import SimpleTestCase

from awcenter.api_errors import api_exception_handler
from awcenter.logging import JsonEventFormatter


def sensitive_exception(module_name="awcenter.test_safe_logging.fixture"):
    """Return a caught exception with synthetic sensitive data in its frames."""

    namespace = {"__name__": module_name}
    source = (
        "def explode():\n"
        "    payload = {'password': 'synthetic-payload-marker'}\n"
        "    credential = 'synthetic-local-marker'\n"
        "    raise RuntimeError('synthetic-message-marker')\n"
    )
    exec(compile(source, "/synthetic-private-path/fixture.py", "exec"), namespace)
    try:
        namespace["explode"]()
    except RuntimeError as error:
        return error


class SafeDiagnosticLoggingTests(SimpleTestCase):
    def test_api_error_outside_except_logs_location_and_preserves_generic_response(self):
        exception = sensitive_exception()
        request = SimpleNamespace(
            request_id="request-safe-123",
            data={"password": "synthetic-request-marker"},
            headers={"Authorization": "synthetic-authorization-marker"},
        )

        with self.assertLogs("awcenter.api_errors", level="ERROR") as captured:
            response = api_exception_handler(exception, {"request": request})

        output = JsonEventFormatter().format(captured.records[0])
        event = json.loads(output)
        self.assertEqual(event["event"], "api.unhandled_exception")
        self.assertEqual(event["request_id"], "request-safe-123")
        self.assertEqual(event.get("exception_type"), "RuntimeError")
        self.assertEqual(
            event["exception_location"],
            {
                "module": "awcenter.test_safe_logging.fixture",
                "function": "explode",
                "line": 4,
            },
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], "INTERNAL_ERROR")
        self.assertEqual(response.data["detail"], "An unexpected server error occurred.")
        self.assertEqual(response.data["request_id"], "request-safe-123")
        self.assertTrue(response.data["retryable"])
        self.assertNotIn("exception_location", response.data)
        for marker in (
            "synthetic-message-marker",
            "synthetic-payload-marker",
            "synthetic-local-marker",
            "synthetic-request-marker",
            "synthetic-authorization-marker",
            "/synthetic-private-path/fixture.py",
            __file__,
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, output)
                self.assertNotIn(marker, captured.output[0])
                self.assertNotIn(marker, json.dumps(response.data))
        self.assertIsNone(captured.records[0].exc_info)

    def test_worker_and_notification_context_is_allowlisted_without_payload(self):
        context = {
            "job_id": "job-safe-123",
            "error_type": "OperationalError",
            "failure_stage": "artifact_publication",
            "delivery_id": "delivery-safe-123",
            "notification_id": "notification-safe-123",
            "payload": {"password": "synthetic-worker-payload-marker"},
            "credential": "synthetic-worker-credential-marker",
        }
        with self.assertLogs("jobs.worker", level="ERROR") as captured:
            logging.getLogger("jobs.worker").error(
                "Unhandled job failure: %s", "OperationalError", extra=context
            )

        output = JsonEventFormatter().format(captured.records[0])
        event = json.loads(output)
        self.assertEqual(event["event"], "Unhandled job failure: OperationalError")
        self.assertEqual(event["job_id"], "job-safe-123")
        self.assertEqual(event.get("error_type"), "OperationalError")
        self.assertEqual(event.get("failure_stage"), "artifact_publication")
        self.assertEqual(event.get("delivery_id"), "delivery-safe-123")
        self.assertEqual(event.get("notification_id"), "notification-safe-123")
        self.assertNotIn("payload", event)
        self.assertNotIn("credential", event)
        self.assertNotIn("synthetic-worker-payload-marker", output)
        self.assertNotIn("synthetic-worker-credential-marker", output)

    def test_exception_without_traceback_omits_location(self):
        with self.assertLogs("awcenter.api_errors", level="ERROR") as captured:
            response = api_exception_handler(RuntimeError("synthetic-message-marker"), {})

        event = json.loads(JsonEventFormatter().format(captured.records[0]))
        self.assertEqual(event.get("exception_type"), "RuntimeError")
        self.assertNotIn("exception_location", event)
        self.assertEqual(response.data["code"], "INTERNAL_ERROR")
        self.assertNotIn("synthetic-message-marker", json.dumps(event))

    def test_non_text_module_metadata_is_not_serialized(self):
        exception = sensitive_exception({"payload": "synthetic-module-payload-marker"})
        with self.assertLogs("awcenter.api_errors", level="ERROR") as captured:
            api_exception_handler(exception, {})

        output = JsonEventFormatter().format(captured.records[0])
        event = json.loads(output)
        self.assertEqual(event["exception_location"]["module"], "<unknown>")
        self.assertNotIn("synthetic-module-payload-marker", output)

    def test_formatter_derives_safe_context_from_existing_exception_info(self):
        exception = sensitive_exception()
        record = logging.LogRecord(
            "jobs.worker", logging.ERROR, "ignored", 1, "worker.failed", (),
            (type(exception), exception, exception.__traceback__),
        )

        output = JsonEventFormatter().format(record)
        event = json.loads(output)
        self.assertEqual(event["exception_type"], "RuntimeError")
        self.assertEqual(
            event["exception_location"],
            {"module": "awcenter.test_safe_logging.fixture", "function": "explode", "line": 4},
        )
        self.assertNotIn("synthetic-message-marker", output)
        self.assertNotIn("/synthetic-private-path/fixture.py", output)

    def test_formatter_projects_only_declared_exception_location_fields(self):
        record = logging.LogRecord(
            "awcenter.api_errors", logging.ERROR, "ignored", 1, "api.failed", (), None,
        )
        record.exception_type = "RuntimeError"
        record.exception_location = {
            "module": "awcenter.test_safe_logging.fixture",
            "function": "explode",
            "line": 4,
            "payload": "synthetic-location-payload-marker",
        }

        output = JsonEventFormatter().format(record)
        event = json.loads(output)
        self.assertEqual(event.get("exception_type"), "RuntimeError")
        self.assertEqual(
            event.get("exception_location"),
            {"module": "awcenter.test_safe_logging.fixture", "function": "explode", "line": 4},
        )
        self.assertNotIn("synthetic-location-payload-marker", output)
