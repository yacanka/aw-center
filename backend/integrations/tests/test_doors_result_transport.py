from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
from unittest.mock import Mock
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from integrations.doors import builder_link, builder_read, checklist
from integrations.doors.builder_common import COMMON_DXL, wrap_dxl
from integrations.doors.client import DoorsClient
from integrations.doors.config import RESULT_MODE_APPLICATION, RESULT_MODE_FILE, DoorsClientConfig
from integrations.doors.exceptions import DoorsDxlError, DoorsOperationError
from integrations.doors.models import OperationResult
from integrations.doors.services import build_client_config
from integrations.doors.transport import APPLICATION_RESULT_PREFIX, DoorsOleTransport


class ApplicationResultTransportTests(SimpleTestCase):
    """Verify the file-free oleSetResult/Application.Result result path."""

    def setUp(self):
        """Create a connected transport with a fake DOORS application."""
        self.transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        self.application = Mock()
        self.transport.application = self.application

    def test_dxl_field_escaping_cannot_consume_following_protocol_separator(self):
        """DXL single-argument calls need outer grouping before concatenation.

        Argument parentheses alone allow the next TAB to enter awc_escape,
        converting a column boundary into literal backslash-t without a DXL error.
        OLE fakes cannot detect this, so guard the generated expressions too.
        """
        linker = builder_link.link_requirements(
            "/Project/Reference", "/Project/Target", "/Project/Links",
            "PoC List", "Requirement", "PoC Info", 0, -1, "ref2tar", False,
        )
        cases = (
            (builder_read.export_module("/Project/Module", 20), '(awc_escape(identifier(awc_object))) "\\t"'),
            (checklist.check_applicable_disciplines("/Project/Module"), '(awc_escape(identifier(object))) "\\t"'),
            (COMMON_DXL, '(awc_escape(code)) "\\t"'),
            (linker, '(awc_escape(awc_group_key)) "\\t"'),
        )
        for script, grouped_call in cases:
            with self.subTest(expression=grouped_call):
                self.assertIn(grouped_call, script)

    def test_export_preserves_escaped_data_and_rejects_an_escaped_column_boundary(self):
        client = DoorsClient(self.transport.config, self.transport)
        for merged_boundary in (False, True):
            identifier_and_level = r"REQ-1\t2" if merged_boundary else "REQ-1\t2"
            payload = (
                "ATTRIBUTE\tObject Text\n"
                f"OBJECT\t1\t{identifier_and_level}\t" + r"Türkçe\ttext\nnext\\tail" + "\n"
                "OK\tEXPORT_MODULE_DONE\n"
            )

            def publish(script):
                prefix = re.search(r'oleSetResult\("(AW_DOORS_RESULT\|[^"]*)"', script).group(1)
                self.application.Result = prefix + payload

            with self.subTest(merged_boundary=merged_boundary):
                self.application.runStr.side_effect = publish
                if merged_boundary:
                    with self.assertRaisesMessage(DoorsDxlError, "malformed object row"):
                        client.export_module("/Project/Module", 20)
                else:
                    exported = client.export_module("/Project/Module", 20)
                    self.assertEqual(exported["results"][0], {
                        "absolute_number": 1, "identifier": "REQ-1", "level": 2,
                        "attributes": {"Object Text": "Türkçe\ttext\nnext\\tail"},
                    })

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

    def test_default_client_uses_application_result_without_creating_a_file(self):
        self.application.runStr.side_effect = self.publish_result
        client = DoorsClient(self.transport.config, self.transport)

        result = client.run_dxl('awc_ok("APPLICATION_RESULT_AVAILABLE")')

        self.assertTrue(result.ok)
        self.assertNotIn("Stream awc_result", self.application.runStr.call_args.args[0])

    def test_module_check_rejects_unexpected_results_instead_of_reporting_access(self):
        client = DoorsClient(self.transport.config, self.transport)
        for payload in (
            "OK", "OK\tOTHER_OPERATION", "OBJECT\t1", "ERR", "OK\tMODULE_OPENED\nextra",
            "ERR\tOPEN_MODULE", "ERR\tOPEN_MODULE\tdetail\textra", "ERR\tOTHER_ERROR\tdetail",
            "ERR\tOPEN_MODULE\tdetail\nOK\tMODULE_OPENED",
            "ERR\tOPEN_MODULE\tdetail\nERR\tOPEN_MODULE\tdetail",
        ):
            def publish(script):
                prefix = re.search(r'oleSetResult\("(AW_DOORS_RESULT\|[^"]*)"', script).group(1)
                self.application.Result = prefix + payload

            with self.subTest(payload=payload):
                self.application.runStr.side_effect = publish
                with self.assertRaises(DoorsDxlError):
                    client.check_module("/Project/Module")

    def test_crud_rejects_unconfirmed_or_mismatched_results(self):
        client = DoorsClient(self.transport.config, self.transport)
        attributes = {"Object Text": "updated"}
        cases = (
            (lambda: client.get_object("/Project/Module", 1, ["Object Text"]),
             "OBJECT\t2\tREQ-2\t1\tother object\n"),
            (lambda: client.get_object("/Project/Module", 1, ["Object Text"]),
             "OBJECT\t1\tREQ-1\t1\tvalue\nOBJECT\t2\tREQ-2\t1\textra\n"),
            (lambda: client.set_object_attributes("/Project/Module", 1, attributes), "OK\n"),
            (lambda: client.set_object_attributes("/Project/Module", 1, attributes), "OK\tMODULE_OPENED\n"),
            (lambda: client.create_object("/Project/Module", "first", None, attributes),
             "CREATED\t2\tREQ-2\t1\n"),
            (lambda: client.create_object("/Project/Module", "first", None, attributes),
             "CREATED\t2\tREQ-2\t1\nOK\tATTRIBUTES_SAVED\n"),
            (lambda: client.list_objects("/Project/Module", ["Object Text"], "entire", 20),
             "OBJECT\t1\tREQ-1\t1\tpartial result\n"),
            (lambda: client.export_module("/Project/Module", 20),
             "ATTRIBUTE\tObject Text\nOBJECT\t1\tREQ-1\t1\tpartial result\n"),
            (lambda: client.get_attr("/Project/Module", "Applicable"),
             "OBJECT\tApplicable\nOK\tOTHER_OPERATION\n"),
        )
        for operation, payload in cases:
            def publish(script):
                prefix = re.search(r'oleSetResult\("(AW_DOORS_RESULT\|[^"]*)"', script).group(1)
                self.application.Result = prefix + payload

            with self.subTest(payload=payload):
                self.application.runStr.side_effect = publish
                with self.assertRaises(DoorsDxlError):
                    operation()

    def test_debug_setting_controls_exact_dxl_console_output_before_execution(self):
        username, password = uuid4().hex, uuid4().hex
        for debug in (False, True):
            for failed in (False, True):
                with self.subTest(debug=debug, failed=failed), override_settings(
                    DEBUG=debug, DOORS_USERNAME=username, DOORS_PASSWORD=password,
                ):
                    client = DoorsClient(build_client_config(), self.transport)
                    output = StringIO()

                    def execute(script):
                        if debug:
                            self.assertIn(script, output.getvalue())
                        else:
                            self.assertEqual(output.getvalue(), "")
                        if failed:
                            raise RuntimeError("private OLE failure")
                        self.publish_result(script)

                    self.application.runStr.side_effect = execute
                    with redirect_stdout(output):
                        if failed:
                            with self.assertRaises(DoorsDxlError):
                                client.run_dxl('awc_ok("APPLICATION_RESULT_AVAILABLE")', RESULT_MODE_APPLICATION)
                        else:
                            client.run_dxl('awc_ok("APPLICATION_RESULT_AVAILABLE")', RESULT_MODE_APPLICATION)
                    if debug:
                        script = self.application.runStr.call_args.args[0]
                        self.assertEqual(output.getvalue(), f"[DOORS run_dxl]\n{script}\n[/DOORS run_dxl]\n")
                        self.assertNotIn("private OLE failure", output.getvalue())
                        self.assertNotIn(username, output.getvalue())
                        self.assertNotIn(password, output.getvalue())
                    else:
                        self.assertEqual(output.getvalue(), "")

    def publish_result(self, _script):
        """Simulate DXL calling oleSetResult after runStr starts."""
        prefix = re.search(r'oleSetResult\("(AW_DOORS_RESULT\|[^"]*)"', _script).group(1)
        self.application.Result = f"{prefix}OK\tAPPLICATION_RESULT_AVAILABLE\n"
