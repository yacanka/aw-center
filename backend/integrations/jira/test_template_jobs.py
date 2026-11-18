"""Exercise enqueue races, snapshot integrity, private output and worker isolation."""

import hashlib
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from django.core.files.base import ContentFile
from django.test import override_settings
from docx import Document
from rest_framework.exceptions import PermissionDenied

from awcenter.job_executors import resolve_job_executor
from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from jobs.worker import claim_next_job, execute_claimed_job

from .template_catalog import jira_server_id
from .template_jobs import JOB_KIND
from .template_models import JiraDocumentTemplate


ENDPOINT = "/api/integrations/jira/document-generation/jobs/"
READ = "integrations.jira.template_jobs.read_template_issue"


@override_settings(JIRA_URL="https://jira.example.test")
class TemplateDocumentJobTests(JobTestCase):
    def setUp(self):
        super().setUp()
        document = Document()
        document.add_paragraph("{{Title}} / {{Note}} / {{Blank}} / {{Missing}}")
        source = BytesIO()
        document.save(source)
        content = source.getvalue()
        self.template = JiraDocumentTemplate.objects.create(
            name="Form", server_id=jira_server_id(), project_id="12", issue_type_id="7",
            project_name="Example", issue_type_name="Sub-task",
            placeholders=[{"name": name, "count": 1} for name in ("Title", "Note", "Blank", "Missing")],
            mapping={"Title": "summary", "Blank": "customfield_10"},
            source_file=ContentFile(content, name="source.docx"),
            source_sha256=hashlib.sha256(content).hexdigest(),
        )
        self.issue = {"issue": "EX-10", "project_id": "12", "issue_type_id": "7", "fields": [
            {"id": "summary", "name": "Summary", "value": "Changed\nTitle", "supported": True},
            {"id": "customfield_10", "name": "Optional", "value": "", "supported": True},
            {"id": "unused", "name": "Unused", "value": "unrelated-data", "supported": True},
        ]}
        self.payload = {"issue": "EX-10", "template_id": str(self.template.pk), "version": 1,
                        "manual_values": {"Note": "<manual>"}}

    def post(self, key="test-generate-a", **changes):
        return self.client.post(ENDPOINT, {**self.payload, **changes}, format="json", HTTP_IDEMPOTENCY_KEY=key)

    def run_worker(self):
        execute_claimed_job(claim_next_job("template-worker", eligible_kinds=(JOB_KIND,)), resolve_job_executor)
        return Job.objects.get()

    @patch(READ)
    def test_frozen_package_survives_catalog_changes_and_only_owner_downloads(self, read):
        read.return_value = self.issue
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        self.template.archived, self.template.version = True, 2
        self.template.save()
        Path(self.template.source_file.path).write_bytes(b"replaced source")
        job = Job.objects.get()
        self.assertEqual(job.kind, JOB_KIND)
        self.assertNotIn("<manual>", str(job.parameters))
        with job.input_file.open("rb") as data, ZipFile(data) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["values"], {"Title": "Changed\nTitle", "Note": "<manual>", "Blank": "", "Missing": ""})
            self.assertNotIn("unrelated-data", str(manifest))
        read.side_effect = AssertionError("Worker and replays must use the captured input")
        replay = self.post(issue="https://jira.example.test/browse/EX-10")
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["id"], response.data["id"])
        self.assertEqual(self.post(manual_values={"Note": "different"}).status_code, 409)
        job = self.run_worker()
        self.assertEqual(job.status, JobStatus.SUCCEEDED, job.message)
        url = self.client.get(f"/api/jobs/{job.id}/").data["download_url"]
        content = b"".join(self.client.get(url).streaming_content)
        self.assertEqual(Document(BytesIO(content)).paragraphs[0].text, "Changed\nTitle / <manual> /  / ")
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(read.call_count, 1)

    @patch(READ)
    def test_enforces_live_authority_match_and_version_before_enqueue(self, read):
        read.side_effect = PermissionDenied()
        self.assertEqual(self.post().status_code, 403)
        read.side_effect = None
        for change in ({"project_id": "other"}, {"issue_type_id": "other"}):
            read.return_value = {**self.issue, **change}
            self.assertEqual(self.post().status_code, 409)
        read.return_value = self.issue
        self.assertEqual(self.post(version=2).status_code, 409)
        self.template.archived = True
        self.template.save()
        self.assertEqual(self.post().status_code, 409)
        self.assertFalse(Job.objects.exists())

    @patch(READ)
    def test_missing_unsupported_or_overridden_mappings_fail(self, read):
        read.return_value = self.issue
        for manual in ({"Title": "override"}, {"Blank": "override"}, {"other": "extra"}, {"Note": 0}):
            self.assertEqual(self.post(manual_values=manual).status_code, 400)
        read.return_value = {**self.issue, "fields": self.issue["fields"][:1]}
        self.assertEqual(self.post().status_code, 409)
        self.issue["fields"][1]["supported"] = False
        read.return_value = self.issue
        self.assertEqual(self.post().status_code, 409)
        self.assertFalse(Job.objects.exists())

    @patch(READ)
    def test_second_request_finishing_issue_read_after_first_enqueued_replays_winner(self, read):
        # Simulate the other request committing during the first request's remote I/O.
        def interleaved_read(*_args):
            with patch(READ, return_value=self.issue):
                self.assertEqual(self.post().status_code, 201)
            return {**self.issue, "fields": []}

        read.side_effect = interleaved_read
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Job.objects.count(), 1)

    @patch(READ)
    def test_concurrent_template_edit_during_remote_read_requires_new_version(self, read):
        def edit_during_jira_read(*_args):
            self.template.version += 1
            self.template.save()
            return self.issue

        read.side_effect = edit_during_jira_read
        self.assertEqual(self.post().status_code, 409)
        self.assertFalse(Job.objects.exists())

    @patch(READ)
    def test_rejected_input_does_not_create_artifacts(self, read):
        self.assertEqual(self.post(key="").status_code, 400)
        self.assertEqual(self.post(version=0).status_code, 400)
        self.assertEqual(self.post(manual_values={"Note": "a" * 32_769}).status_code, 400)
        self.assertEqual(self.post(file="document-snapshot.zip").status_code, 400)
        read.assert_not_called()
        self.assertFalse(Job.objects.exists())

    @patch(READ)
    def test_snapshot_tampering_cannot_publish(self, read):
        read.return_value = self.issue
        self.assertEqual(self.post().status_code, 201)
        Path(Job.objects.get().input_file.path).write_bytes(b"tampered")
        job = self.run_worker()
        self.assertEqual(job.error_code, "JOB_INPUT_CORRUPT")
        self.assertFalse(job.output_file)
