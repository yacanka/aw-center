from pathlib import Path
from unittest.mock import Mock

from django.test import SimpleTestCase

from integrations.doors.builder_common import wrap_dxl
from integrations.doors.client import DoorsClient
from integrations.doors.config import RESULT_MODE_APPLICATION, RESULT_MODE_FILE, DoorsClientConfig
from integrations.doors.exceptions import DoorsOperationError
from integrations.doors.models import OperationResult
from integrations.doors.transport import APPLICATION_RESULT_PREFIX, DoorsOleTransport


class ApplicationResultTransportTests(SimpleTestCase):
    """Verify the file-free oleSetResult/Application.Result result path."""

    def setUp(self):
        """Create a connected transport with a fake DOORS application."""
        self.transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        self.application = Mock()
        self.transport.application = self.application

    def test_application_result_script_has_no_result_stream(self):
        """Application.Result mode publishes the buffer without a temp file."""
        script = wrap_dxl('awc_ok("PROBE")', None, RESULT_MODE_APPLICATION)

        self.assertIn('oleSetResult("AW_DOORS_RESULT|" stringOf(awc_result))', script)
        self.assertNotIn("Stream awc_result", script)

    def test_file_script_opens_result_stream_before_operation(self):
        """File mode preserves incremental output for backward compatibility."""
        script = wrap_dxl('awc_ok("FILE")', Path("result.txt"), RESULT_MODE_FILE)

        self.assertLess(script.index("Stream awc_result"), script.index('awc_ok("FILE")'))
        self.assertIn("close awc_result", script)

    def test_transport_reads_application_result_lines(self):
        """Python reads the line protocol directly from Application.Result."""
        self.application.runStr.side_effect = self.publish_result
        client = DoorsClient(self.transport.config, self.transport)

        result = client.probe_application_result()

        self.assertEqual(result.raw_lines, ("OK\tAPPLICATION_RESULT_AVAILABLE",))
        script = self.application.runStr.call_args.args[0]
        self.assertIn('awc_ok("APPLICATION_RESULT_AVAILABLE")', script)

    def test_operation_error_keeps_dxl_reason(self):
        """The Windows-side adapter retains structured DXL diagnostics."""
        result = OperationResult(False, "ERR\tOPEN_MODULE\tAccess denied", ())

        with self.assertRaisesMessage(
            DoorsOperationError,
            "DOORS operation failed (OPEN_MODULE): Access denied",
        ):
            DoorsClient.raise_on_error(result)

    def publish_result(self, _script):
        """Simulate DXL calling oleSetResult after runStr starts."""
        self.application.Result = f"{APPLICATION_RESULT_PREFIX}OK\tAPPLICATION_RESULT_AVAILABLE\n"
