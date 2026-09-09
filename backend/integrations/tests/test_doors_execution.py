"""API-to-artifact DOORS regressions with only the desktop COM boundary faked."""

import hashlib
import json
import re
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

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

    def execute_operation(self, route, values, payloads):
        response = self.client.post(
            f"/api/integrations/doors/{route}/", values, format="json",
            HTTP_IDEMPOTENCY_KEY=f"{route}-{Job.objects.count()}",
        )
        self.assertEqual(response.status_code, 201, response.data)
        job = Job.objects.get(pk=response.data["id"])
        application = ResultApplication(payloads)
        automation = Mock()
        automation.GetActiveObject.return_value = application
        with (
            patch("integrations.doors.services.initialized_com", return_value=nullcontext()),
            patch("integrations.doors.transport.DoorsOleTransport.load_automation", return_value=automation),
            patch("integrations.doors.transport.DoorsOleTransport.is_client_running", return_value=True),
        ):
            execute_claimed_job(claim_next_job("doors-worker:test", [job.kind]), resolve_worker_executor)
        job.refresh_from_db()
        self.assertTrue(all(not path.exists() for path in application.result_files))
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
