"""Exercise desktop lifecycle and generated-result contracts without IBM DOORS."""

import json
import os
import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from awcenter.job_executors import worker_job_timeout
from integrations.doors import builder_read, builder_write, checklist
from integrations.doors.builder_common import wrap_dxl
from integrations.doors.client import DoorsClient
from integrations.doors.config import DoorsClientConfig
from integrations.doors.exceptions import DoorsConnectionError, DoorsDxlError
from integrations.doors.job_executor import execute_doors_job
from integrations.doors.services import build_client_config, execute_with_client
from integrations.doors.startup import parse_server_executable, registered_executable
from integrations.doors.transport import DoorsOleTransport, DxlExecution
from jobs.contracts import JobExecutionFailure


class ReadyApplication:
    """Fake only OLE; execute the real connection and result-reading code."""

    def __init__(self):
        self.Result = ""
        self.scripts = []

    def runStr(self, script):
        self.scripts.append(script)
        if script.startswith("oleSetResult("):
            self.Result = json.loads(script[len("oleSetResult("):-1])


class DoorsDesktopLifecycleTests(SimpleTestCase):
    def test_prog_id_can_resolve_executable_without_explicit_path(self):
        with patch("integrations.doors.transport.registered_executable", return_value=Path("doors.exe")) as resolve:
            transport = DoorsOleTransport(DoorsClientConfig(ole_program_id="DOORS.Application.9"))
            self.assertEqual(transport.start_command(), ["doors.exe"])
            resolve.assert_called_once_with("DOORS.Application.9")

    def test_registry_resolution_checks_both_views_and_ignores_server_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "doors.exe"
            executable.touch()
            registry = Mock(KEY_READ=1, KEY_WOW64_64KEY=256, KEY_WOW64_32KEY=512)
            registry.OpenKey.side_effect = [OSError(), nullcontext("class"), nullcontext("server")]
            registry.QueryValueEx.side_effect = [("class-id", 1), (f'"{executable}" /automation', 1)]
            with patch.dict("sys.modules", {"winreg": registry}):
                self.assertEqual(registered_executable("DOORS.Application"), executable)
            self.assertEqual(registry.OpenKey.call_count, 3)

    def test_registry_parser_supports_paths_with_spaces_without_replaying_flags(self):
        for command in ('"C:\\Program Files\\IBM\\doors.exe" /automation', 'C:\\Program Files\\IBM\\doors.exe -x'):
            self.assertEqual(str(parse_server_executable(command)), r"C:\Program Files\IBM\doors.exe")
        with self.assertRaises(ValueError):
            parse_server_executable("not-an-executable")

    def test_starts_once_with_settings_credentials_and_keeps_desktop_open(self):
        credential = uuid4().hex
        application = ReadyApplication()
        automation = Mock()
        automation.GetActiveObject.side_effect = [RuntimeError(), application, application]
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "doors.exe"
            executable.touch()
            config = DoorsClientConfig(str(executable), username="automation", password=credential)
            transport = DoorsOleTransport(config)
            with (
                patch.object(transport, "load_automation", return_value=automation),
                patch.object(transport, "is_client_running", return_value=False),
                patch("integrations.doors.transport.subprocess.Popen") as start,
            ):
                transport.connect()
                transport.application = None  # The disposable executor releases its proxy.
                transport.connect()
            start.assert_called_once()
            argv = start.call_args.args[0]
            self.assertEqual(argv[:3], [str(executable), "-user", "automation"])
            self.assertTrue(argv[-1] == credential)
            self.assertEqual(argv[-2], "-password")
            self.assertNotIn("-batch", argv)
            self.assertNotIn(credential, repr(config))
            self.assertEqual(len(application.scripts), 2)
            self.assertTrue(all(script.startswith("oleSetResult(") for script in application.scripts))
            start.return_value.terminate.assert_not_called()
            start.return_value.kill.assert_not_called()
            automation.Dispatch.assert_not_called()

    def test_disabled_auto_start_never_launches_missing_client(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe", auto_start_client=False))
        with (
            patch.object(transport, "load_automation"),
            patch.object(transport, "get_active_application", return_value=None),
            patch.object(transport, "is_client_running", return_value=False),
            patch("integrations.doors.transport.subprocess.Popen") as start,
            self.assertRaises(DoorsConnectionError),
        ):
            transport.connect()
        start.assert_not_called()

    def test_start_failure_does_not_expose_command_or_credentials(self):
        credential = uuid4().hex
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "doors.exe"
            executable.touch()
            transport = DoorsOleTransport(DoorsClientConfig(str(executable), username="automation", password=credential))
            with (
                patch("integrations.doors.transport.subprocess.Popen", side_effect=OSError(credential)),
                self.assertRaises(DoorsConnectionError) as raised,
            ):
                transport.start_client(Mock())
            self.assertNotIn(credential, str(raised.exception))
            self.assertTrue(raised.exception.__suppress_context__)

    def test_invalid_configuration_is_rejected_before_client_start(self):
        for values in (
            {"ole_program_id": ""}, {"startup_timeout_seconds": float("nan")},
            {"run_timeout_seconds": 601}, {"result_mode": "unknown"},
            {"max_result_bytes": 0}, {"password": uuid4().hex},
        ):
            with self.assertRaises(ValueError):
                DoorsClientConfig(**values)

    def test_waits_for_authenticated_dxl_readiness_not_just_com_registration(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        application = ReadyApplication()
        with (
            patch.object(transport, "get_active_application", return_value=application),
            patch.object(transport, "application_ready", side_effect=[False, True]) as ready,
            patch("integrations.doors.transport.time.sleep"),
        ):
            self.assertIs(transport.wait_for_application(Mock()), application)
        self.assertEqual(ready.call_count, 2)

    def test_readiness_timeout_does_not_run_business_dxl(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe", startup_timeout_seconds=1))
        application = Mock()
        application.runStr.side_effect = RuntimeError()
        with (
            patch.object(transport, "get_active_application", return_value=application),
            patch("integrations.doors.transport.time.monotonic", side_effect=[0, 0, 2]),
            patch("integrations.doors.transport.time.sleep"),
            self.assertRaises(DoorsConnectionError) as raised,
        ):
            transport.wait_for_application(Mock())
        self.assertEqual(raised.exception.code, "DOORS_STARTUP_TIMEOUT")
        self.assertTrue(application.runStr.call_args.args[0].startswith("oleSetResult("))

    def test_process_inspection_is_limited_to_worker_windows_session(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        inspector = Mock()
        inspector.Win32_Process.side_effect = [[SimpleNamespace(SessionId=4)], []]
        with patch.object(transport, "load_process_inspector", return_value=lambda: inspector):
            self.assertFalse(transport.is_client_running())
        self.assertEqual(inspector.Win32_Process.call_args_list[0].kwargs, {"ProcessId": os.getpid()})
        self.assertEqual(inspector.Win32_Process.call_args.kwargs, {"SessionId": 4})

    def test_multiple_clients_fail_closed(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        inspector = Mock()
        inspector.Win32_Process.side_effect = [
            [SimpleNamespace(SessionId=4)],
            [SimpleNamespace(Name="doors.exe"), SimpleNamespace(Name="DOORS.EXE")],
        ]
        with (
            patch.object(transport, "load_process_inspector", return_value=lambda: inspector),
            self.assertRaises(DoorsConnectionError) as raised,
        ):
            transport.is_client_running()
        self.assertEqual(raised.exception.code, "DOORS_MULTIPLE_CLIENTS")

    def test_com_proxy_is_released_before_apartment_is_closed_even_on_failure(self):
        client = Mock()
        with (
            patch("integrations.doors.services.initialized_com", return_value=nullcontext()),
            patch("integrations.doors.services.DoorsClient", return_value=client),
            self.assertRaises(DoorsDxlError),
        ):
            execute_with_client(lambda _: (_ for _ in ()).throw(DoorsDxlError("failed")))
        self.assertIsNone(client.transport.application)
        client.transport.close.assert_not_called()

    def test_environment_credentials_reach_client_without_repr_exposure(self):
        credential = uuid4().hex
        with override_settings(DOORS_USERNAME="automation", DOORS_PASSWORD=credential):
            config = build_client_config()
        self.assertEqual(config.username, "automation")
        self.assertTrue(config.password == credential)
        self.assertNotIn(credential, repr(config))

    @override_settings(DOORS_STARTUP_TIMEOUT_SECONDS=90, DOORS_RUN_TIMEOUT_SECONDS=120)
    def test_parent_budget_includes_startup_and_multi_run_operations(self):
        self.assertEqual(worker_job_timeout("doors.run_dxl", True), 465)
        self.assertEqual(worker_job_timeout("doors.create_object", True), 225)

    @override_settings(DOORS_ENABLED=True)
    def test_connection_failure_is_sanitized_and_not_an_ambiguous_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "input.json", root / "result.json"
            source.write_text("{}")
            detail = uuid4().hex
            task = Mock(side_effect=DoorsConnectionError(detail, "DOORS_STARTUP_TIMEOUT"))
            with (
                patch("integrations.doors.job_executor.materialize_job_input", return_value=source),
                patch("integrations.doors.job_executor.temporary_output", return_value=output),
                patch.dict("integrations.doors.job_executor.DOORS_TASKS", {"doors.update_object": task}),
                self.assertRaises(JobExecutionFailure) as raised,
            ):
                execute_doors_job(SimpleNamespace(kind="doors.update_object", reconcile_on_lease_loss=True))
            self.assertEqual(raised.exception.code, "DOORS_STARTUP_TIMEOUT")
            self.assertNotIn(detail, str(raised.exception))
            self.assertFalse(source.exists())
            self.assertFalse(output.exists())


class DoorsResultIntegrityTests(SimpleTestCase):
    def test_application_result_rejects_stale_execution_token(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        with (
            patch.object(transport, "read_status", side_effect=["AW_DOORS_RESULT|old|OK\told", "AW_DOORS_RESULT|new|OK\tcurrent"]),
            patch("integrations.doors.transport.time.sleep"),
        ):
            self.assertEqual(transport.read_application_execution(result_token="new").lines, ("OK\tcurrent",))

    def test_partial_file_without_footer_is_never_successful(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe", run_timeout_seconds=1))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            output.write_text("OK\tpartial\n")
            with (
                patch.object(transport, "read_status", return_value="AW_DOORS_RUNNING|pending"),
                patch("integrations.doors.transport.time.monotonic", side_effect=[0, 0, 2]),
                patch("integrations.doors.transport.time.sleep"),
                self.assertRaises(DoorsDxlError),
            ):
                transport.read_file_execution(output)

    def test_file_completion_requires_exact_path_and_reads_closed_utf8_result(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            output.write_text("OK\tTürkçe\n", encoding="utf-8")
            with (
                patch.object(transport, "read_status", side_effect=["AW_DOORS_OK|another-file", f"AW_DOORS_OK|{output}"]),
                patch("integrations.doors.transport.time.sleep"),
            ):
                self.assertEqual(transport.read_file_execution(output).lines, ("OK\tTürkçe",))

    def test_result_limits_and_encoding_fail_closed(self):
        transport = DoorsOleTransport(DoorsClientConfig("doors.exe", max_result_bytes=1024))
        for payload in (b"x" * 1025, b"\xff"):
            with self.subTest(size=len(payload)), self.assertRaises(DoorsDxlError):
                transport.decode_result_lines(payload)
        self.assertEqual(transport.decode_result_lines("OBJECT\ttext\u2028value\r\n".encode()), ("OBJECT\ttext\u2028value",))

    def test_empty_result_does_not_report_success(self):
        transport = Mock()
        transport.run_dxl.return_value = DxlExecution("done", ())
        client = DoorsClient(DoorsClientConfig("doors.exe"), transport)
        with self.assertRaises(DoorsDxlError):
            client.check_module("/Project/Module")

    def test_malformed_rows_are_rejected_without_partial_attribute_mapping(self):
        for line in ("OBJECT\tx\tREQ\t1\ttext", "OBJECT\t1\tREQ\tbad\ttext", "OBJECT\t1\tREQ\t1"):
            with self.subTest(line=line), self.assertRaises(DoorsDxlError):
                DoorsClient.parse_object(line, ["Object Text"])
        with self.assertRaises(DoorsDxlError):
            DoorsClient.parse_info("OBJECT")

    def test_attribute_lookup_quotes_search_and_copies_name_before_close(self):
        script = builder_read.get_attr("/Project/Module", 'Applicable"\ntext')
        self.assertIn('"Applicable\\"\\ntext"', script)
        self.assertLess(script.index("awc_name = awc_attribute.name"), script.index("close(module"))
        self.assertIn("ATTRIBUTE_AMBIGUOUS", script)
        self.assertIn('awc_emit("OBJECT\\t" awc_escape(awc_name))', script)

    def test_all_read_and_write_builders_preserve_open_modules_and_valid_result_sink(self):
        scripts = [
            builder_read.check_module("/Project/Module"),
            builder_read.list_objects("/Project/Module", ["Object Text"], "entire", 20),
            builder_read.get_object("/Project/Module", 1, ["Object Text"]),
            builder_read.export_module("/Project/Module", 20),
            checklist.check_applicable_disciplines("/Project/Module"),
        ]
        for script in scripts:
            self.assertIn("if (awc_owns_module) close(module, false)", script)
            wrapped = wrap_dxl(script, Path("result.txt"), "file")
            self.assertIn("write(awc_result_file, CP_UTF8)", wrapped)
        for script in (
            builder_write.set_object_attributes("/Project/Module", 1, {"Object Text": "value"}),
            builder_write.create_object("/Project/Module", "first", None, {"Object Text": "value"}),
        ):
            self.assertIn("MODULE_ALREADY_OPEN", script)
            self.assertIn('awc_error("SAVE_MODULE", awc_save_error)', script)
