"""Recovery tests for analysis-to-JIRA publication side effects."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import Permission

from jobs.tests.base import JobTestCase

from dcc.issue_draft_publisher import publish_to_jira
from dcc.test_issue_drafts import create_analysis_job, create_metadata


class JiraIssueDraftRecoveryTests(JobTestCase):
    """Verify replay safety after lost HTTP responses and JIRA timeouts."""

    @patch("dcc.issue_draft_services.publish_to_jira", return_value="CHN-501")
    def test_publish_request_replays_confirmed_result_without_second_jira_call(self, publisher):
        """A lost success response cannot duplicate the external issue."""

        job = create_analysis_job(self.user)
        created = self.client.post("/dcc/issue-drafts/", {"source_job_id": job.id}).data
        approved = self.client.post(
            f"/dcc/issue-drafts/{created['id']}/approve/", {"version": created["version"]}
        ).data
        self.user.user_permissions.add(Permission.objects.get(codename="publish_jiraissuedraft"))
        payload = {"version": approved["version"], "JSESSIONID": "session-credential"}

        first = self.client.post(f"/dcc/issue-drafts/{created['id']}/publish/", payload)
        replay = self.client.post(f"/dcc/issue-drafts/{created['id']}/publish/", payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["jira_issue_key"], "CHN-501")
        publisher.assert_called_once()

    def test_job_detail_exposes_only_existing_draft_reference(self):
        """Job Center can reopen a draft without receiving its private content in job lists."""

        job = create_analysis_job(self.user)
        draft = self.client.post("/dcc/issue-drafts/", {"source_job_id": job.id}).data

        response = self.client.get(f"/jobs/{job.id}/")

        self.assertEqual(response.data["jira_draft"]["id"], draft["id"])
        self.assertNotIn("description", response.data["jira_draft"])

    def test_owner_deletion_cascades_source_job_and_draft(self):
        """Draft provenance cannot block the intentional account deletion lifecycle."""

        job = create_analysis_job(self.user)
        self.client.post("/dcc/issue-drafts/", {"source_job_id": job.id})

        self.user.delete()

        self.assertFalse(type(job).objects.filter(pk=job.pk).exists())

    @patch("dcc.issue_draft_publisher.JiraConnector")
    def test_new_issue_carries_unique_recovery_and_provenance_labels(self, connector_class):
        """Every create can be rediscovered safely after an uncertain response."""

        client = connector_class.return_value
        client.find_issue_by_label.return_value = None
        client.get_create_fields.return_value = create_metadata()
        client.create_issue.return_value = SimpleNamespace(key="CHN-502")
        draft = SimpleNamespace(
            marker_label="aw-center-unique", project_key="CHN",
            summary="Review", description="Explainable finding",
            extra_fields={"customfield_10001": "100"},
        )

        issue_key = publish_to_jira(draft, "session-credential")

        fields = client.create_issue.call_args.args[0]
        self.assertEqual(issue_key, "CHN-502")
        self.assertIn("aw-center-unique", fields["labels"])
        self.assertEqual(fields["issuetype"], {"name": "Task"})
