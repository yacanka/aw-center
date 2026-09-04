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
from .subtask_contracts import sanitize_subtask_fields, validate_item_field_contract
from .subtask_jobs import JOB_KIND, enqueue_subtask_batch, enqueue_subtask_resume
from .subtask_serializers import SubtaskBatchSerializer
from .subtask_views import workbook_items


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

    def test_original_dynamic_builtin_fields_are_available_without_target_overrides(self):
        metadata = sanitize_subtask_fields([
            {"id": identifier, "name": identifier, "schema": {"type": schema_type}}
            for identifier, schema_type in (
                ("project", "string"), ("parent", "string"), ("issuetype", "string"),
                ("summary", "string"), ("description", "string"),
                ("assignee", "user"), ("duedate", "date"),
            )
        ])
        self.assertEqual(
            [field["id"] for field in metadata], ["description", "assignee", "duedate"]
        )

    def test_original_saved_list_shape_round_trips_through_user_preferences(self):
        lists = [{
            "title": "Review checklist",
            "fields": [
                {"id": "description", "name": "Description", "schema": {"type": "string"}},
                {"id": "duedate", "name": "Due Date", "schema": {"type": "date"}},
            ],
            "list": [{
                "summary": "Review", "assignee": "reviewer",
                "fields": {"description": "Details", "duedate": "2026-09-30"},
            }],
        }]
        saved = self.client.patch(
            "/api/users/preferences/", {"jira_list": lists}, format="json"
        )
        self.assertEqual(saved.status_code, 200)
        loaded = self.client.get("/api/users/preferences/")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.data["jira_list"], lists)

    def test_main_branch_option_values_and_new_option_ids_both_validate(self):
        metadata = sanitize_subtask_fields([{
            "id": "customfield_10001", "name": "Category",
            "schema": {"type": "option"},
            "allowedValues": [{"id": "100", "value": "Review", "self": "https://invalid.test/private"}],
        }])
        self.assertEqual(metadata[0]["allowedValues"], [
            {"value": "Review", "id": "100", "label": "Review"}
        ])
        for value in ("Review", "100"):
            validate_item_field_contract(
                [{"summary": "Review", "fields": {"customfield_10001": value}}], metadata
            )

    def test_required_builtin_columns_use_normalized_item_values(self):
        from rest_framework.exceptions import ValidationError

        metadata = sanitize_subtask_fields([
            {
                "id": identifier, "name": identifier, "required": True,
                "schema": {"type": schema_type},
            }
            for identifier, schema_type in (
                ("description", "string"), ("assignee", "user"), ("duedate", "date")
            )
        ])
        serializer = SubtaskBatchSerializer(data={
            "issue": "CHN-42", "items": [{
                "summary": "Review", "description": "Details", "assignee": "reviewer",
                "due_date": "2026-09-30", "fields": {},
            }],
        })
        serializer.is_valid(raise_exception=True)
        validate_item_field_contract(serializer.validated_data["items"], metadata)
        with self.assertRaises(ValidationError):
            validate_item_field_contract([{"summary": "Review", "fields": {}}], metadata)

    def test_reserved_markers_and_target_overrides_remain_rejected(self):
        for fields in (
            {"parent": "CHN-99"}, {"project": "OTHER"}, {"issuetype": "Task"},
            {"labels": ["awcenter-st-forged-1"]},
            {"labels": ["AWCENTER-ST-forged-1"]},
        ):
            with self.subTest(fields=fields):
                serializer = SubtaskBatchSerializer(data={
                    "issue": "CHN-42", "items": [{"summary": "Review", "fields": fields}],
                })
                self.assertFalse(serializer.is_valid())

    def test_original_excel_date_formats_and_blank_optional_cells(self):
        from datetime import datetime

        mapping = [
            {"column": column, "field": field}
            for column, field in (
                ("Title", "summary"), ("Details", "description"),
                ("Owner", "assignee"), ("Due", "duedate"),
            )
        ]
        dates = [
            "30.09.2026", "30/09/2026", "2026-09-30", "30-09-2026",
            "30 09 2026", "30 September 2026", "30 Sep 2026", datetime(2026, 9, 30),
        ]
        items = workbook_items(
            workbook_upload(
                [" Title ", "Details", "Owner", "Due"],
                [[f"Review {index}", None, None, value] for index, value in enumerate(dates)],
            ),
            mapping,
        )
        self.assertEqual(len(items), len(dates))
        for item in items:
            self.assertEqual(item["description"], "")
            self.assertEqual(item["assignee"], "")
            self.assertEqual(item["due_date"], "2026-09-30")
        serializer = SubtaskBatchSerializer(data={"issue": "CHN-42", "items": items})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_excel_invalid_dates_are_reported_instead_of_silently_discarded(self):
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            workbook_items(
                workbook_upload(["Title", "Due"], [["Review", "31.02.2026"]]),
                [{"column": "Title", "field": "summary"}, {"column": "Due", "field": "duedate"}],
            )

    @patch("dcc.subtask_executor.require_jira_session")
    @patch("dcc.subtask_executor.jira_connector_for")
    def test_dynamic_labels_are_preserved_alongside_server_markers(self, connector_for, _session):
        source, _created = enqueue_subtask_batch(
            self.user, "CHN-42", [self.project],
            [{"summary": "Review", "fields": {"labels": ["review"]}}],
            "subtask-labels-001",
        )
        client = Mock()
        client.find_issue_by_label.return_value = None
        client.get_subtask_fields.return_value = [{
            "id": "labels", "name": "Labels", "required": True,
            "schema": {"type": "array", "items": "string"},
        }]
        client.create_subtask_from_fields.return_value = SimpleNamespace(key="CHN-100")
        connector_for.return_value = client
        claimed = claim_next_job("subtask-worker", eligible_kinds=(JOB_KIND,))
        with bind_execution(claimed):
            result = execute_jira_subtask_batch(claimed)
        labels = client.build_subtask_fields.call_args.args[4]["labels"]
        self.assertEqual(labels, [
            "review", f"awcenter-st-{source.parameters['operation_id']}-1", "aw-center-subtask"
        ])
        result.path.unlink(missing_ok=True)


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
