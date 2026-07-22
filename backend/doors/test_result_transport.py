from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .client.builder_common import wrap_dxl
from .client.client import DoorsClient
from .client.config import RESULT_MODE_APPLICATION, RESULT_MODE_FILE, DoorsClientConfig
from .client.exceptions import DoorsOperationError
from .client.models import OperationResult
from .client.transport import APPLICATION_RESULT_PREFIX, DoorsOleTransport


class ApplicationResultTransportTests(SimpleTestCase):
    """Verify the file-free oleSetResult/Application.Result result path."""

    def setUp(self):
        """Create a connected transport with a fake DOORS application."""
        self.transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        self.application = Mock()
        self.transport.application = self.application

    def test_application_result_script_has_no_result_stream(self):
        """Application.Result mode publishes the buffer without a temp file."""
        script = wrap_dxl('__aw_ok("PROBE")', None, RESULT_MODE_APPLICATION)

        self.assertIn('oleSetResult("AW_DOORS_RESULT|" stringOf(__aw_result))', script)
        self.assertNotIn("Stream __aw_result", script)

    def test_file_script_opens_result_stream_before_operation(self):
        """File mode preserves incremental output for backward compatibility."""
        script = wrap_dxl('__aw_ok("FILE")', Path("result.txt"), RESULT_MODE_FILE)

        self.assertLess(script.index("Stream __aw_result"), script.index('__aw_ok("FILE")'))
        self.assertIn("close __aw_result", script)

    def test_transport_reads_application_result_lines(self):
        """Python reads the line protocol directly from Application.Result."""
        self.application.runStr.side_effect = self.publish_result
        client = DoorsClient(self.transport.config, self.transport)

        result = client.probe_application_result()

        self.assertEqual(result.raw_lines, ("OK\tAPPLICATION_RESULT_AVAILABLE",))
        script = self.application.runStr.call_args.args[0]
        self.assertIn('__aw_ok("APPLICATION_RESULT_AVAILABLE")', script)

    def test_operation_error_keeps_dxl_reason(self):
        """DXL error codes and reasons remain visible to API callers."""
        result = OperationResult(False, "ERR\tOPEN_MODULE\tAccess denied", ())

        with self.assertRaisesMessage(
            DoorsOperationError,
            "DOORS operation failed (OPEN_MODULE): Access denied",
        ):
            DoorsClient.raise_on_error(result)

    def publish_result(self, _script):
        """Simulate DXL calling oleSetResult after runStr starts."""
        self.application.Result = f"{APPLICATION_RESULT_PREFIX}OK\tAPPLICATION_RESULT_AVAILABLE\n"


class DoorsErrorDetailApiTests(TestCase):
    """Verify that actionable DOORS errors reach authenticated users."""

    def setUp(self):
        """Create an authenticated API caller."""
        self.client = APIClient()
        user = get_user_model().objects.create_user(username="doors-detail-user")
        self.client.force_authenticate(user)

    @patch("doors.api_views.execute_with_client")
    def test_operation_reason_is_returned_in_standard_error_detail(self, execute_client):
        """The API no longer replaces a DXL reason with a generic message."""
        execute_client.side_effect = DoorsOperationError(
            "DOORS operation failed (OPEN_MODULE): Access denied",
            code="OPEN_MODULE",
        )

        response = self.client.post(
            reverse("doors_check_module"),
            {"module_path": "/Project/Restricted"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.data["detail"],
            "DOORS operation failed (OPEN_MODULE): Access denied",
        )
        self.assertEqual(response.data["code"], "DOORS_OPERATION_FAILED")

    def test_application_result_probe_requires_administrator(self):
        """The diagnostic cannot be invoked by a normal authenticated user."""
        response = self.client.post(reverse("doors_application_result_probe"), format="json")

        self.assertEqual(response.status_code, 403)
