"""Exercise a real DOCX through the meeting, draft and subtask job boundaries."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document

from awcenter.job_executors import resolve_job_executor
from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from jobs.worker import claim_next_job, execute_claimed_job
from orgs.models import Person, Project, ProjectRoleAssignment

from .meeting_views import match_directory_assignees
from .meeting_jobs import MEETING_JOB_KIND
from .subtask_jobs import JOB_KIND as SUBTASK_KIND
from .test_issue_draft_recovery import ready_connector


def word_bytes(with_table=True):
    document = Document()
    if with_table:
        meeting = document.add_table(rows=11, cols=4)
        meeting.cell(2, 2).text = "Design review"
        meeting.cell(3, 2).text = "MOM-42"
        meeting.cell(9, 0).merge(meeting.cell(9, 3)).text = "Görüşmeler ve kararlar"
        meeting.cell(10, 0).text = "Review complete."
        document.add_paragraph("Follow-up agreed.")
        actions = document.add_table(rows=5, cols=4)
        actions.cell(0, 0).merge(actions.cell(0, 3)).text = "İşlem Maddeleri"
        for row, values in enumerate((
            ("No", "Action Item", "Responsible", "Due Date"),
            ("1", "Update checklist", "Review team", "20.11.2026"),
        ), start=1):
            for col, value in enumerate(values):
                actions.cell(row, col).text = value
        actions.cell(3, 0).merge(actions.cell(3, 3)).text = "Ekler"
        actions.cell(4, 0).text = "Appendix"
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


class MeetingMinutesTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.get(slug="hys")
        ProjectRoleAssignment.objects.create(
            user=self.user, project=self.project, domain="jira", role="publisher",
        )

    def upload(self, data, name="minutes.docx"):
        return self.client.post(
            "/api/integrations/jira/meeting-minutes/jobs/",
            {"file": SimpleUploadedFile(name, data, content_type="application/octet-stream")},
        )

    def execute(self, kind):
        job = claim_next_job("meeting-test-worker", eligible_kinds=(kind,))
        self.assertIsNotNone(job)
        execute_claimed_job(job, resolve_job_executor)
        job.refresh_from_db()
        return job

    def test_unsupported_upload_and_unauthorized_upload_leave_no_job(self):
        self.assertEqual(self.upload(b"invalid").status_code, 400)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.upload(word_bytes()).status_code, 403)
        self.assertFalse(Job.objects.exists())

    def test_incomplete_action_row_fails_without_shifting_the_next_responsible(self):
        document = Document(BytesIO(word_bytes()))
        actions = document.tables[1]
        actions.cell(2, 1).merge(actions.cell(2, 2))
        buffer = BytesIO()
        document.save(buffer)
        self.assertEqual(self.upload(buffer.getvalue()).status_code, 201)
        result = self.execute(MEETING_JOB_KIND)
        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertEqual(result.error_code, "MEETING_MINUTES_INVALID")

    def test_suggests_only_unambiguous_directory_ids(self):
        Person.objects.create(name="Review team", person_id="team-a", email="a@example.invalid")
        action = {"responsible": "Review team"}
        self.assertEqual(match_directory_assignees([action])[0]["assignee"], "team-a")
        Person.objects.create(name="Review team", person_id="team-b", email="b@example.invalid")
        self.assertEqual(match_directory_assignees([action])[0]["assignee"], "")

    def test_cancelled_read_can_be_restarted_without_duplicating_the_new_attempt(self):
        data = word_bytes()
        first = self.upload(data)
        self.assertEqual(self.client.post(f"/api/jobs/{first.data['id']}/cancel/").status_code, 200)
        retry = self.upload(data)
        self.assertEqual(retry.status_code, 201)
        self.assertNotEqual(first.data["id"], retry.data["id"])
        self.assertEqual(self.upload(data).data["id"], retry.data["id"])

    def test_tableless_minutes_fail_without_producing_a_draft(self):
        self.assertEqual(self.upload(word_bytes(False)).status_code, 201)
        job = self.execute(MEETING_JOB_KIND)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_code, "MEETING_MINUTES_INVALID")
        self.assertFalse(job.output_file)

    def test_review_publish_and_replay(self):
        data = word_bytes()
        self.assertEqual(self.upload(data).status_code, 201)
        self.assertEqual(self.upload(data).status_code, 200)
        job = self.execute(MEETING_JOB_KIND)
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        root = "/api/integrations/jira/"
        draft = self.client.post(root + "issue-drafts/", {
            "source_job_id": str(job.id), "project_key": "CHN", "project_slugs": [self.project.slug],
        }, format="json").data
        self.assertEqual(draft["summary"], "Design review")
        self.assertIn("Review complete.\nFollow-up agreed.", draft["description"])
        actions_url = f"{root}meeting-minutes/{draft['id']}/actions/"
        self.assertEqual(self.client.get(actions_url).status_code, 400)
        draft_url = f"{root}issue-drafts/{draft['id']}/"
        approved = self.client.post(draft_url + "approve/", {"version": draft["version"]})
        self.assertEqual(approved.status_code, 200)
        publication = self.client.post(draft_url + "publish/", {"version": approved.data["version"]},
                                       HTTP_IDEMPOTENCY_KEY="meeting-publish-attempt")
        self.assertEqual(publication.status_code, 201)
        connector = ready_connector()
        connector.create_issue.return_value = SimpleNamespace(key="CHN-42")
        with (
            patch("integrations.jira.publication_executor.jira_connector_for", return_value=connector),
            patch("integrations.jira.publication_executor.require_jira_session"),
        ):
            self.assertEqual(self.execute("dcc.publish_jira_draft").status, JobStatus.SUCCEEDED)
        connector.create_issue.assert_called_once()
        connector.get_subtask_fields.return_value = []
        with patch("integrations.jira.meeting_views.jira_connector_for", return_value=connector):
            actions = self.client.get(actions_url).data["actions"]
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["action_item"], "Update checklist")
            payload = {"items": [{"summary": actions[0]["action_item"], "due_date": "2026-11-20"}]}
            first = self.client.post(actions_url, payload, format="json")
            self.assertEqual(first.status_code, 201)
            replay = self.client.post(actions_url, payload, format="json")
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(first.data["id"], replay.data["id"])
            self.assertEqual(self.client.get(actions_url).data["job_id"], first.data["id"])
        connector.create_subtask_from_fields.return_value = SimpleNamespace(key="CHN-43")
        with (
            patch("integrations.jira.subtask_executor.jira_connector_for", return_value=connector),
            patch("integrations.jira.subtask_executor.require_jira_session"),
        ):
            self.assertEqual(self.execute(SUBTASK_KIND).status, JobStatus.SUCCEEDED)
        connector.set_issue.assert_called_with("CHN-42")
        connector.create_subtask_from_fields.assert_called_once()
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(actions_url).status_code, 404)
