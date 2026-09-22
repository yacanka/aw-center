"""Live metadata mapping and typed Excel import regressions."""

import json
from datetime import datetime
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from integrations.jira.field_values import encode_value
from jobs.models import Job
from jobs.tests.base import JobTestCase
from orgs.models import Project

from .subtask_contracts import sanitize_subtask_fields
from .subtask_views import workbook_items
from .test_subtask_jobs import workbook_upload


def field(identifier, kind, **extras):
    return {"id": identifier, "name": identifier, "schema": {"type": kind}, **extras}


class WorkbookFieldTests(SimpleTestCase):
    def test_summary_is_opt_in_and_target_fields_remain_protected(self):
        fields = [field(key, "string") for key in ("summary", "project", "parent", "issuetype", "description")]
        self.assertEqual([item["id"] for item in sanitize_subtask_fields(fields)], ["description"])
        self.assertEqual([item["id"] for item in sanitize_subtask_fields(fields, include_summary=True)], ["summary", "description"])

    def test_live_schema_decodes_dates_lists_references_and_preserves_text(self):
        fields = [
            field("summary", "string"),
            field("customfield_101", "array"),
            field("customfield_102", "date"),
            field("customfield_103", "option"),
            field("customfield_104", "string"),
            field("customfield_105", "boolean"),
        ]
        fields[1]["schema"]["items"] = "number"
        mapping = [{"column": item["id"], "field": item["id"]} for item in fields]
        rows = [["Review", '0; 2.5', datetime(2026, 9, 22), '{"id":"12"}', '[keep; text]', False]]
        items = workbook_items(workbook_upload([item["id"] for item in fields], rows), mapping, metadata=fields)
        values = items[0]["fields"]
        self.assertEqual(values["customfield_101"], ["0", "2.5"])
        self.assertEqual(encode_value(values["customfield_101"], fields[1]), [0, 2.5])
        self.assertEqual(values["customfield_102"], "2026-09-22")
        self.assertEqual(values["customfield_103"], {"id": "12"})
        self.assertEqual(values["customfield_104"], '[keep; text]')
        self.assertFalse(encode_value(values["customfield_105"], fields[5]))

    def test_json_arrays_preserve_delimiters_in_option_names(self):
        metadata = [field("summary", "string"), field("components", "array")]
        metadata[1]["schema"]["items"] = "component"
        rows = [["Review", '["Engine; Main", {"id":"12"}]']]
        items = workbook_items(workbook_upload(["Title", "Components"], rows), [
            {"column": "Title", "field": "summary"}, {"column": "Components", "field": "components"},
        ], metadata=metadata)
        self.assertEqual(items[0]["fields"]["components"], ["Engine; Main", {"id": "12"}])

    def test_invalid_date_and_json_identify_excel_row_and_column(self):
        for kind, value in (("date", "31.02.2026"), ("array", '["broken"'), ("datetime", datetime(2026, 9, 22))):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValidationError, "Excel row 2, column 'Value'"):
                workbook_items(workbook_upload(["Title", "Value"], [["Review", value]]), [
                    {"column": "Title", "field": "summary"}, {"column": "Value", "field": "customfield_101"},
                ], metadata=[field("summary", "string"), field("customfield_101", kind)])

    def test_empty_unavailable_columns_cannot_bypass_live_mapping_validation(self):
        with self.assertRaisesRegex(ValidationError, "unavailable fields: parent"):
            workbook_items(workbook_upload(["Title", "Parent"], [["Review", None]]), [
                {"column": "Title", "field": "summary"}, {"column": "Parent", "field": "parent"},
            ], metadata=[field("summary", "string")])


@override_settings(JIRA_ENABLED=True)
class WorkbookMappingApiTests(JobTestCase):
    @patch("dcc.subtask_views.inspect_subtask_target")
    def test_field_inspection_requests_live_summary_for_workbook_only(self, inspect_target):
        inspect_target.return_value = (Mock(), "CHN-42", [], [field("summary", "string")])
        response = self.client.post('/api/dcc/subtasks/fields/', {"issue": "CHN-42", "include_summary": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["fields"][0]["id"], "summary")
        self.assertTrue(inspect_target.call_args.kwargs["include_summary"])

    @patch("dcc.subtask_views.inspect_subtask_target")
    def test_workbook_queues_custom_fields_against_the_selected_task(self, inspect_target):
        metadata = [field("summary", "string"), field("customfield_123", "array", required=True)]
        metadata[1]["schema"]["items"] = "option"
        metadata[1]["allowedValues"] = [{"id": "12", "value": "Review"}]
        inspect_target.return_value = (Mock(), "CHN-42", [Project.objects.get(slug="hys")], metadata)
        response = self.client.post('/api/dcc/subtasks/jobs/', {
            "issue": "CHN-42",
            "mapping": json.dumps([{"column": "Title", "field": "summary"}, {"column": "Category", "field": "customfield_123"}]),
            "file": workbook_upload(["Title", "Category"], [["Review", "Review"]]),
        }, format="multipart", HTTP_IDEMPOTENCY_KEY="workbook-live-fields")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(inspect_target.call_args.kwargs["include_summary"])
        with Job.objects.get(pk=response.data["id"]).input_file.open('rb') as stored:
            item = json.load(stored)["items"][0]
        self.assertEqual(item["fields"], {"customfield_123": ["Review"]})
        self.assertEqual(item["description"], '')

    @patch("dcc.subtask_views.inspect_subtask_target")
    def test_changed_target_requirements_block_before_enqueue(self, inspect_target):
        metadata = [field("summary", "string"), field("customfield_123", "option", required=True)]
        inspect_target.return_value = (Mock(), "CHN-43", [Project.objects.get(slug="hys")], metadata)
        response = self.client.post('/api/dcc/subtasks/jobs/', {
            "issue": "CHN-43", "mapping": json.dumps([{"column": "Title", "field": "summary"}]),
            "file": workbook_upload(["Title"], [["Review"]]),
        }, format="multipart", HTTP_IDEMPOTENCY_KEY="workbook-required-field")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Job.objects.exists())
