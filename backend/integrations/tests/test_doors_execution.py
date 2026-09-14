"""API-to-artifact DOORS regressions with only the desktop COM boundary faked."""

import hashlib
import json
import os
import re
from contextlib import nullcontext, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import override_settings

from awcenter.job_executors import resolve_worker_executor
from integrations.tests.test_doors_lifecycle import ReadyApplication
from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from jobs.worker import claim_next_job, execute_claimed_job


class ResultApplication(ReadyApplication):
    def __init__(self, payloads):
        super().__init__()
        self.payloads = iter(payloads)
        self.result_files = []

    def runStr(self, script):
        super().runStr(script)
        if script.startswith("oleSetResult("):
            return
        payload = next(self.payloads)
        if 'Buffer awc_result = create' in script:
            prefix = re.search(r'oleSetResult\("(AW_DOORS_RESULT\|[^"]*)"', script).group(1)
            self.Result = prefix + payload
            return
        match = re.search(r'string awc_result_file = ("(?:[^"\\]|\\.)*")', script)
        output = Path(json.loads(match.group(1)))
        self.result_files.append(output)
        output.write_text(payload, encoding="utf-8")
        self.Result = f"AW_DOORS_OK|{output}"


@override_settings(DOORS_ENABLED=True, DOORS_EXECUTABLE="doors.exe", DOORS_RESULT_MODE="file")
class DoorsExecutionPipelineTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        status = patch("integrations.doors.api_views.integration_status", return_value={
            "configured": True, "available": True, "active_workers": 1,
            "transport": "windows-worker",
        })
        status.start()
        self.addCleanup(status.stop)

    def execute_operation(self, route, values, payloads, *, start_client=False, windows_filesystem=False):
        response = self.client.post(
            f"/api/integrations/doors/{route}/", values, format="json",
            HTTP_IDEMPOTENCY_KEY=f"{route}-{Job.objects.count()}",
        )
        self.assertEqual(response.status_code, 201, response.data)
        job = Job.objects.get(pk=response.data["id"])
        application = ResultApplication(payloads)
        automation = Mock()
        automation.GetActiveObject.side_effect = [RuntimeError(), application] if start_client else None
        automation.GetActiveObject.return_value = application
        config_platform = SimpleNamespace(platform="win32" if windows_filesystem else "linux")
        original_open = os.open
        executable = self.media_directory / "doors.exe"
        executable.touch()

        def open_file(path, flags, mode=0o777):
            if windows_filesystem and Path(path).is_dir():
                raise PermissionError("Windows cannot open directory handles through os.open")
            return original_open(path, flags, mode)

        with (
            patch("integrations.doors.services.initialized_com", return_value=nullcontext()),
            patch("integrations.doors.transport.DoorsOleTransport.load_automation", return_value=automation),
            patch("integrations.doors.transport.DoorsOleTransport.is_client_running", return_value=not start_client),
            patch("integrations.doors.transport.DoorsOleTransport.executable", executable),
            patch("integrations.doors.transport.subprocess.Popen") as start,
            patch("jobs.artifacts.sys", config_platform),
            patch("jobs.artifacts.os.open", side_effect=open_file),
        ):
            execute_claimed_job(claim_next_job("doors-worker:test", [job.kind]), resolve_worker_executor)
        job.refresh_from_db()
        self.assertTrue(all(not path.exists() for path in application.result_files))
        if start_client:
            start.assert_called_once()
        else:
            start.assert_not_called()
        if route == "module-check-jobs" or settings.DOORS_RESULT_MODE == "application_result":
            self.assertFalse(application.result_files)
        return job

    def download_success(self, job):
        self.assertEqual(job.status, JobStatus.SUCCEEDED, job.message)
        self.assertEqual(job.progress, 100)
        response = self.client.get(f"/api/jobs/{job.id}/download/")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content)
        self.assertEqual(hashlib.sha256(content).hexdigest(), job.output_sha256)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(f"/api/jobs/{job.id}/download/").status_code, 404)
        self.client.force_authenticate(self.user)
        return json.loads(content)

    def test_all_read_operations_publish_owned_verified_artifacts(self):
        values = {"module_path": "/Project/Module"}
        cases = [
            ("module-check-jobs", values, ["OK\tMODULE_OPENED\n"], "accessible"),
            ("object-list-jobs", values, ["OBJECT\t1\tREQ-1\t1\tHeading\tTürkçe\\ntext\nOK\tLIST_OBJECTS_DONE\n"], "count"),
            ("object-detail-jobs", {**values, "absolute_number": 1}, ["OBJECT\t1\tREQ-1\t1\tHeading\tText\n"], "absolute_number"),
            ("module-export-jobs", values, ["ATTRIBUTE\tObject Text\nOBJECT\t1\tREQ-1\t1\tTürkçe\nOK\tEXPORT_MODULE_DONE\n"], "count"),
            ("discipline-check-jobs", values, ["OBJECT\tApplicable\nOK\tATTRIBUTE_FOUND\n", "OBJECT\tDiscipline\nOK\tATTRIBUTE_FOUND\n", "OBJECT\t1\tREQ-1\t1\tApplicable\t\nOK\tDISCIPLINE_CHECK_DONE\n"], "count"),
        ]
        for route, data, payloads, expected_key in cases:
            with self.subTest(route=route):
                payload = self.download_success(self.execute_operation(route, data, payloads))
                self.assertEqual(payload[expected_key], 1)

    def test_update_and_create_publish_confirmed_writes(self):
        values = {"module_path": "/Project/Module", "attributes": {"Object Text": "value"}}
        update = self.execute_operation("object-update-jobs", {**values, "absolute_number": 1}, ["OK\tATTRIBUTES_SAVED\n"])
        self.assertTrue(self.download_success(update)["updated"])
        created = self.execute_operation("object-create-jobs", {**values, "position": "first"}, ["CREATED\t2\tREQ-2\t1\nOK\tOBJECT_CREATED\n"])
        self.assertEqual(self.download_success(created)["absolute_number"], 2)

    def test_linker_preview_and_write_keep_reconciliation_contract(self):
        values = {
            "ref_module_name": "/Project/Reference", "target_module_name": "/Project/Target",
            "link_module_name": "/Project/Links", "ref_attr_poc": "PoC", "ref_attr_req": "Requirement",
            "target_attr_poc": "PoC", "start_index": 0, "text_length": -1, "direction": "ref2tar",
            "activeness": False,
        }
        output = "GROUP\tP1\tREQ-1\nTARGET\tP1\nSUMMARY\t1\t1\t1\t1\t0\t0\t0\nOK\tREQUIREMENT_LINKER_DONE\n"
        job = self.execute_operation("requirement-link-jobs", values, [output])
        self.assertFalse(job.reconcile_on_lease_loss)
        self.assertEqual(self.download_success(job)["mode"], "preview")
        values["activeness"] = True
        job = self.execute_operation("requirement-link-jobs", values, ["ERR\tCREATE_LINK\tupstream detail\n"])
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertFalse(job.retryable)
        self.assertFalse(job.output_file)
        self.assertNotIn("upstream detail", job.message)

    def test_read_error_returns_stable_code_without_upstream_data(self):
        job = self.execute_operation("module-check-jobs", {"module_path": "/Project/Module"}, ["ERR\tOPEN_MODULE\tprivate upstream detail\n"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "DOORS_OPEN_MODULE")
        self.assertNotIn("private upstream detail", job.message)
        self.assertFalse(job.output_file)

    @override_settings(DOORS_RESULT_MODE="file")
    def test_module_check_uses_file_free_transport_for_success_and_missing_module(self):
        success = self.execute_operation(
            "module-check-jobs",
            {"module_path": "/Project/Existing"},
            ["OK\tMODULE_OPENED\n"],
        )
        self.assertTrue(self.download_success(success)["accessible"])

        missing = self.execute_operation(
            "module-check-jobs",
            {"module_path": "/Project/Missing"},
            ["ERR\tOPEN_MODULE\tModule was not found\n"],
        )
        self.assertEqual(missing.status, JobStatus.FAILED)
        self.assertEqual(missing.error_code, "DOORS_OPEN_MODULE")
        self.assertFalse(missing.output_file)

    def test_open_desktop_module_is_a_known_write_rejection(self):
        job = self.execute_operation("object-update-jobs", {
            "module_path": "/Project/Module", "absolute_number": 1,
            "attributes": {"Object Text": "value"},
        }, ["ERR\tMODULE_ALREADY_OPEN\tClose the module first\nERR\tOPEN_MODULE_EDIT\t\\N\n"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "DOORS_MODULE_ALREADY_OPEN")
        self.assertFalse(job.output_file)

    def test_non_object_payloads_are_validation_errors_before_queueing(self):
        for route in ("module-check-jobs", "requirement-link-jobs"):
            with self.subTest(route=route):
                response = self.client.post(
                    f"/api/integrations/doors/{route}/", [{"module_path": "/Project/Module"}],
                    format="json", HTTP_IDEMPOTENCY_KEY=route,
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Job.objects.exists())

    @override_settings(DOORS_RESULT_MODE="application_result")
    def test_file_free_result_mode_uses_the_same_job_artifact_contract(self):
        job = self.execute_operation("module-check-jobs", {"module_path": "/Project/Module"}, ["OK\tMODULE_OPENED\n"])
        self.assertTrue(self.download_success(job)["accessible"])

    def test_module_check_on_windows_for_running_and_new_clients(self):
        for start_client in (False, True):
            for exists in (False, True):
                with self.subTest(start_client=start_client, exists=exists):
                    payload = "OK\tMODULE_OPENED\n" if exists else "ERR\tOPEN_MODULE\tprivate detail\n"
                    job = self.execute_operation(
                        "module-check-jobs", {"module_path": "/Project/Module"}, [payload],
                        start_client=start_client, windows_filesystem=True,
                    )
                    if exists:
                        self.assertTrue(self.download_success(job)["accessible"])
                    else:
                        self.assertEqual(job.status, JobStatus.FAILED)
                        self.assertEqual(job.error_code, "DOORS_OPEN_MODULE")
                        self.assertFalse(job.output_file)
                        self.assertNotIn("private detail", job.message)
                        response = self.client.get(f"/api/jobs/{job.id}/")
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.data["error_code"], "DOORS_OPEN_MODULE")
                        self.assertIn("read permission", response.data["recovery_hint"])
                        self.assertIsNone(response.data["download_url"])

    def test_invalid_module_result_fails_without_publishing_an_artifact(self):
        job = self.execute_operation("module-check-jobs", {"module_path": "/Project/Module"}, ["OK\tOTHER_OPERATION\n"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "DOORS_DXL_FAILED")
        self.assertFalse(job.output_file)


@override_settings(DOORS_RESULT_MODE="application_result")
class DoorsApplicationResultPipelineTests(DoorsExecutionPipelineTests):
    """Run the same read/write/artifact contracts through the preferred OLE channel."""

    def test_object_reads_preserve_unicode_escaped_delimiters_and_null_attributes(self):
        response = self.download_success(self.execute_operation(
            "object-detail-jobs",
            {"module_path": "/Project/Module", "absolute_number": 1, "attributes": ["Object Text", "Optional"]},
            ["OBJECT\t1\tREQ-1\t1\tTürkçe\\talan\\nsatır\\rdönüş\\\\yol 🛫\u2028son\t\\N\n"],
        ))
        self.assertEqual(response["attributes"], {
            "Object Text": "Türkçe\talan\nsatır\rdönüş\\yol 🛫\u2028son", "Optional": None,
        })

    def test_all_create_positions_publish_the_confirmed_object(self):
        attributes = {"Object Text": 'Türkçe "alıntı"\nmetin', "Count": 2, "Enabled": True}
        for position in ("first", "after", "before", "below", "below_last"):
            with self.subTest(position=position):
                values = {"module_path": "/Project/Module", "position": position, "attributes": attributes}
                if position != "first":
                    values["relative_absolute_number"] = 1
                result = self.download_success(self.execute_operation(
                    "object-create-jobs", values, ["CREATED\t2\tREQ-2\t1\nOK\tOBJECT_CREATED\n"],
                ))
                self.assertEqual(result["absolute_number"], 2)
                self.assertEqual(result["attributes"], attributes)

    def test_crud_failures_never_publish_unconfirmed_results(self):
        module = {"module_path": "/Project/Module"}
        read = {**module, "absolute_number": 1, "attributes": ["Object Text"]}
        update = {**module, "absolute_number": 1, "attributes": {"Object Text": "updated"}}
        create = {**module, "position": "first", "attributes": {"Object Text": "created"}}
        cases = (
            ("object-detail-jobs", read, "ERR\tOBJECT_NOT_FOUND\tprivate detail\n", JobStatus.FAILED, "DOORS_OBJECT_NOT_FOUND"),
            ("object-detail-jobs", read, "OBJECT\t2\tREQ-2\t1\twrong object\n", JobStatus.FAILED, "DOORS_DXL_FAILED"),
            ("object-update-jobs", update, "ERR\tOBJECT_NOT_FOUND\tprivate detail\n", JobStatus.FAILED, "DOORS_OBJECT_NOT_FOUND"),
            ("object-update-jobs", update, "ERR\tSAVE_MODULE\tprivate detail\n", JobStatus.RECONCILIATION_REQUIRED, "RECONCILIATION_REQUIRED"),
            ("object-update-jobs", update, "OK\tMODULE_OPENED\n", JobStatus.RECONCILIATION_REQUIRED, "RECONCILIATION_REQUIRED"),
            ("object-create-jobs", create, "ERR\tOPEN_MODULE_EDIT\tprivate detail\n", JobStatus.FAILED, "DOORS_OPEN_MODULE_EDIT"),
            ("object-create-jobs", create, "ERR\tCREATE_OBJECT\tprivate detail\n", JobStatus.RECONCILIATION_REQUIRED, "RECONCILIATION_REQUIRED"),
            ("object-create-jobs", create, "CREATED\t2\tREQ-2\t1\n", JobStatus.RECONCILIATION_REQUIRED, "RECONCILIATION_REQUIRED"),
        )
        for route, values, payload, status, code in cases:
            with self.subTest(route=route, payload=payload):
                job = self.execute_operation(route, values, [payload])
                self.assertEqual(job.status, status)
                self.assertEqual(job.error_code, code)
                self.assertFalse(job.output_file)
                self.assertNotIn("private detail", job.message)
                if status == JobStatus.RECONCILIATION_REQUIRED:
                    self.assertFalse(job.retryable)

    @override_settings(DOORS_MAX_RESULT_BYTES=1024)
    def test_oversized_crud_results_fail_without_file_fallback_or_write_retry(self):
        module = {"module_path": "/Project/Module"}
        cases = (
            ("object-detail-jobs", {**module, "absolute_number": 1}, JobStatus.FAILED),
            ("object-update-jobs", {**module, "absolute_number": 1, "attributes": {"Object Text": "updated"}}, JobStatus.RECONCILIATION_REQUIRED),
            ("object-create-jobs", {**module, "position": "first", "attributes": {"Object Text": "created"}}, JobStatus.RECONCILIATION_REQUIRED),
        )
        for route, values, status in cases:
            with self.subTest(route=route):
                job = self.execute_operation(route, values, ["ğ" * 513])
                self.assertEqual(job.status, status)
                self.assertFalse(job.output_file)
                if status == JobStatus.RECONCILIATION_REQUIRED:
                    self.assertFalse(job.retryable)

    @override_settings(DEBUG=True)
    def test_debug_echoes_crud_scripts_only_to_worker_console(self):
        module = {"module_path": "/Project/Module"}
        cases = (
            ("object-detail-jobs", {**module, "absolute_number": 1}, "OBJECT\t1\tREQ-1\t1\tHeading\tText\n", "Object object = object(1, module)"),
            ("object-update-jobs", {**module, "absolute_number": 1, "attributes": {"Object Text": "updated"}}, "OK\tATTRIBUTES_SAVED\n", 'awc_ok("ATTRIBUTES_SAVED")'),
            ("object-create-jobs", {**module, "position": "first", "attributes": {"Object Text": "created"}}, "CREATED\t2\tREQ-2\t1\nOK\tOBJECT_CREATED\n", 'awc_ok("OBJECT_CREATED")'),
        )
        for route, values, payload, statement in cases:
            with self.subTest(route=route):
                output = StringIO()
                with redirect_stdout(output):
                    job = self.execute_operation(route, values, [payload])
                self.assertEqual(job.status, JobStatus.SUCCEEDED)
                self.assertIn(statement, output.getvalue())
                self.assertIn("Buffer awc_result = create", output.getvalue())
                self.assertEqual(output.getvalue().count("[DOORS run_dxl]"), 1)
                response = self.client.get(f"/api/jobs/{job.id}/")
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("pragma runLim", str(response.data))
                self.assertNotIn("pragma runLim", json.dumps(self.download_success(job)))
