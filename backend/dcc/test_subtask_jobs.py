"""Credential, authorization, idempotency, and recovery tests for JIRA subtasks."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from openpyxl import Workbook

from jobs.execution import bind_execution
from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from jobs.worker import claim_next_job, execute_claimed_job
from orgs.models import Project, ProjectRoleAssignment

from .subtask_executor import execute_jira_subtask_batch
from .subtask_jobs import JOB_KIND, enqueue_subtask_batch, enqueue_subtask_resume


@override_settings(JIRA_ENABLED=True)
class JiraSubtaskJobTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.get(slug="hys")
        ProjectRoleAssignment.objects.create(
            user=self.user,
            project=self.project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=ProjectRoleAssignment.Role.OPERATOR,
        )

    @patch("dcc.subtask_views.inspect_subtask_target")
    def test_api_queues_credential_free_manual_plan(self, inspect_target):
        inspect_target.return_value = (Mock(), "CHN-42", [self.project], [])

        response = self.client.post(
            "/api/dcc/subtasks/jobs/",
            {
                "issue": "CHN-42",
                "items": [
                    {
                        "summary": "Panel review",
                        "description": "Review the panel",
                        "assignee": "user.name",
                        "fields": {},
                    }
                ],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="subtask-manual-001",
        )

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.kind, JOB_KIND)
        self.assertNotIn("JSESSIONID", json.dumps(job.parameters))
        with job.input_file.open("rb") as stored:
            self.assertNotIn(b"JSESSIONID", stored.read())

    @patch("dcc.subtask_views.inspect_subtask_target")
    def test_api_rejects_legacy_session_before_jira_access(self, inspect_target):
        response = self.client.post(
            "/api/dcc/subtasks/jobs/",
            {
                "issue": "CHN-42",
                "JSESSIONID": "must-not-be-accepted",
                "items": [{"summary": "Panel review", "fields": {}}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="subtask-legacy-001",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        inspect_target.assert_not_called()

    @patch("dcc.subtask_views.inspect_subtask_target")
    def test_api_rejects_value_outside_live_jira_field_contract(self, inspect_target):
        inspect_target.return_value = (
            Mock(),
            "CHN-42",
            [self.project],
            [
                {
                    "id": "customfield_10001",
                    "name": "Category",
                    "required": True,
                    "hasDefaultValue": False,
                    "schema": {"type": "option"},
                    "allowedValues": [{"value": "100", "label": "Review"}],
                }
            ],
        )

        response = self.client.post(
            "/api/dcc/subtasks/jobs/",
            {
                "issue": "CHN-42",
                "items": [
                    {
                        "summary": "Panel review",
                        "fields": {"customfield_10001": "not-advertised"},
                    }
                ],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="subtask-invalid-field-001",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Job.objects.exists())

    @patch("dcc.subtask_views.inspect_subtask_target")
    def test_workbook_is_normalized_to_private_json_job_input(self, inspect_target):
        inspect_target.return_value = (Mock(), "CHN-42", [self.project], [])
        response = self.client.post(
            "/api/dcc/subtasks/jobs/",
            {
                "issue": "CHN-42",
                "mapping": json.dumps(
                    [
                        {"column": "Title", "field": "summary"},
                        {"column": "Details", "field": "description"},
                    ]
                ),
                "file": workbook_upload(
                    ["Title", "Details"],
                    [["Panel review", "Review the panel"]],
                ),
            },
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="subtask-workbook-001",
        )

        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.input_name, "jira-subtask-batch.json")
        with job.input_file.open("rb") as stored:
            payload = json.load(stored)
        self.assertEqual(payload["items"][0]["summary"], "Panel review")
        self.assertNotIn("source.xlsx", job.input_file.name)

    @patch("dcc.subtask_executor.require_jira_session")
    @patch("dcc.subtask_executor.jira_connector_for")
    def test_executor_reuses_marker_and_creates_only_missing_subtask(
        self, connector_for, _require_session
    ):
        job, _created = enqueue_subtask_batch(
            self.user,
            "CHN-42",
            [self.project],
            [
                {"summary": "Existing", "fields": {}},
                {
                    "summary": "Missing",
                    "fields": {"customfield_10001": "100"},
                },
            ],
            "subtask-executor-001",
        )
        existing = SimpleNamespace(key="CHN-100")
        created = SimpleNamespace(key="CHN-101")
        client = Mock()
        client.find_issue_by_label.side_effect = [existing, None]
        client.get_subtask_fields.return_value = [
            {
                "id": "customfield_10001",
                "name": "Category",
                "required": False,
                "hasDefaultValue": False,
                "schema": {"type": "option"},
                "allowedValues": [{"id": "100", "value": "Review"}],
            }
        ]
        client.build_subtask_fields.return_value = {"summary": "Missing"}
        client.create_subtask_from_fields.return_value = created
        connector_for.return_value = client
        claimed = claim_next_job("subtask-worker", eligible_kinds=(JOB_KIND,))

        with bind_execution(claimed):
            result = execute_jira_subtask_batch(claimed)

        self.assertEqual(result.summary["created_count"], 1)
        self.assertEqual(result.summary["reused_count"], 1)
        client.create_subtask_from_fields.assert_called_once()
        self.assertEqual(
            client.build_subtask_fields.call_args.args[4]["customfield_10001"],
            {"id": "100"},
        )
        result.path.unlink(missing_ok=True)

    @patch("dcc.subtask_executor.require_jira_session")
    @patch("dcc.subtask_executor.jira_connector_for")
    def test_uncertain_create_is_terminal_reconciliation(self, connector_for, _require_session):
        job, _created = enqueue_subtask_batch(
            self.user,
            "CHN-42",
            [self.project],
            [{"summary": "Uncertain", "fields": {}}],
            "subtask-uncertain-001",
        )
        client = Mock()
        client.find_issue_by_label.return_value = None
        client.get_subtask_fields.return_value = []
        client.build_subtask_fields.return_value = {"summary": "Uncertain"}
        client.create_subtask_from_fields.side_effect = TimeoutError("provider timeout")
        connector_for.return_value = client
        claimed = claim_next_job("subtask-worker", eligible_kinds=(JOB_KIND,))

        execute_claimed_job(claimed, lambda _kind: execute_jira_subtask_batch)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertFalse(job.retryable)

    @patch("dcc.subtask_jobs.require_jira_session")
    def test_explicit_resume_preserves_original_marker_operation(self, _require_session):
        source, _created = enqueue_subtask_batch(
            self.user,
            "CHN-42",
            [self.project],
            [{"summary": "Uncertain", "fields": {}}],
            "subtask-resume-source-001",
        )
        source.status = JobStatus.RECONCILIATION_REQUIRED
        source.save(update_fields=("status",))

        resumed, created = enqueue_subtask_resume(
            self.user,
            source.id,
            "subtask-resume-attempt-001",
        )

        self.assertTrue(created)
        self.assertEqual(resumed.source_job, source)
        self.assertEqual(resumed.parameters["mode"], "resume")
        self.assertEqual(
            resumed.parameters["operation_id"],
            source.parameters["operation_id"],
        )
        with resumed.input_file.open("rb") as stored:
            payload = json.load(stored)
        self.assertEqual(payload["operation_id"], source.parameters["operation_id"])


def workbook_upload(columns, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(columns)
    for row in rows:
        sheet.append(row)
    from io import BytesIO

    content = BytesIO()
    workbook.save(content)
    return SimpleUploadedFile(
        "source.xlsx",
        content.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
