"""Security and lifecycle tests for analysis-to-JIRA issue drafts."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.test import TestCase

from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase

from dcc.issue_draft_models import JiraIssueDraft, JiraIssueDraftStatus
from dcc.issue_draft_contracts import JiraDraftPreflightBlocked
from dcc.issue_draft_publisher import publish_to_jira


class JiraIssueDraftApiTests(JobTestCase):
    """Verify ownership, review gates, concurrency, and safe publication failures."""

    def setUp(self):
        """Extend the isolated job fixture with one completed analysis report."""

        super().setUp()
        self.job = create_analysis_job(self.user)

    def test_create_is_owner_scoped_idempotent_and_uses_verified_report(self):
        """One source report produces one private explainable draft."""

        first = self.client.post("/dcc/issue-drafts/", {"source_job_id": self.job.id})
        second = self.client.post("/dcc/issue-drafts/", {"source_job_id": self.job.id})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertIn("Approval evidence", first.data["description"])
        self.assertEqual(second.headers["Idempotency-Replayed"], "true")
        self.assertEqual(JiraIssueDraft.objects.count(), 1)

    def test_other_owner_cannot_create_or_read_draft(self):
        """Source and draft identifiers do not cross ownership boundaries."""

        created = self.create_draft()
        self.client.force_authenticate(self.other_user)

        create_response = self.client.post("/dcc/issue-drafts/", {"source_job_id": self.job.id})
        detail_response = self.client.get(f"/dcc/issue-drafts/{created['id']}/")

        self.assertEqual(create_response.status_code, 404)
        self.assertEqual(detail_response.status_code, 404)

    def test_corrupt_analysis_output_is_rejected_before_draft_creation(self):
        """Stored bytes must match the worker fingerprint before reuse."""

        self.job.output_sha256 = "0" * 64
        self.job.save(update_fields=["output_sha256"])

        response = self.client.post("/dcc/issue-drafts/", {"source_job_id": self.job.id})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(JiraIssueDraft.objects.count(), 0)

    def test_edit_uses_version_and_invalidates_approval(self):
        """Stale writes fail and approved content cannot change silently."""

        draft = self.create_draft()
        approved = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/approve/", {"version": draft["version"]}
        ).data
        payload = draft_update_payload(approved, summary="Revised review")
        updated = self.client.patch(
            f"/dcc/issue-drafts/{draft['id']}/", payload, format="json"
        ).data
        stale = self.client.patch(f"/dcc/issue-drafts/{draft['id']}/", payload, format="json")

        self.assertEqual(updated["status"], JiraIssueDraftStatus.DRAFT)
        self.assertEqual(updated["summary"], "Revised review")
        self.assertEqual(stale.status_code, 409)

    def test_publish_requires_dedicated_permission_and_approval(self):
        """Owning a draft alone never authorizes the external side effect."""

        draft = self.create_draft()
        forbidden = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/publish/",
            {"version": draft["version"], "JSESSIONID": "session-credential"},
        )
        forbidden_preflight = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/preflight/",
            {"JSESSIONID": "session-credential"},
        )
        self.user.user_permissions.add(Permission.objects.get(codename="publish_jiraissuedraft"))
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)
        unapproved = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/publish/",
            {"version": draft["version"], "JSESSIONID": "session-credential"},
        )

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden_preflight.status_code, 403)
        self.assertEqual(unapproved.status_code, 409)

    @patch("dcc.issue_draft_services.publish_to_jira", return_value="CHN-321")
    def test_approved_draft_publishes_without_persisting_session(self, publisher):
        """A privileged explicit decision stores only the confirmed issue key."""

        draft = self.approved_draft_with_permission()
        response = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/publish/",
            {"version": draft["version"], "JSESSIONID": "session-credential"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], JiraIssueDraftStatus.PUBLISHED)
        self.assertEqual(response.data["jira_issue_key"], "CHN-321")
        self.assertNotIn("session-credential", json.dumps(response.data, default=str))
        self.assertNotIn("session-credential", str(JiraIssueDraft.objects.values().first()))
        publisher.assert_called_once()

    @patch("dcc.issue_draft_services.publish_to_jira", side_effect=RuntimeError("secret endpoint"))
    def test_publish_failure_is_retryable_and_sanitized(self, _publisher):
        """External details never escape while approval remains retryable."""

        draft = self.approved_draft_with_permission()
        response = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/publish/",
            {"version": draft["version"], "JSESSIONID": "session-credential"},
        )

        persisted = JiraIssueDraft.objects.get(pk=draft["id"])
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret endpoint", json.dumps(response.data))
        self.assertEqual(persisted.status, JiraIssueDraftStatus.FAILED)
        self.assertIsNotNone(persisted.approved_at)

    @patch("dcc.issue_draft_views.JiraConnector")
    def test_preflight_exposes_required_fields_without_persisting_session(self, connector_class):
        """Live metadata is sanitized while the transient credential is discarded."""

        draft = self.create_draft()
        self.grant_publish_permission()
        connector_class.return_value.get_create_fields.return_value = create_metadata()

        response = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/preflight/",
            {"JSESSIONID": "session-credential"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["ready"])
        self.assertEqual(response.data["missing_fields"][0]["id"], "customfield_10001")
        self.assertNotIn("session-credential", json.dumps(response.data))
        self.assertNotIn("session-credential", str(JiraIssueDraft.objects.values().first()))

    @patch("dcc.issue_draft_views.JiraConnector", side_effect=RuntimeError("private JIRA detail"))
    def test_preflight_connection_failure_is_sanitized(self, _connector_class):
        """JIRA and credential details never escape a failed metadata inspection."""

        draft = self.create_draft()
        self.grant_publish_permission()

        response = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/preflight/",
            {"JSESSIONID": "session-credential"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "JIRA_DRAFT_PREFLIGHT_UNAVAILABLE")
        self.assertNotIn("private JIRA detail", json.dumps(response.data))
        self.assertNotIn("session-credential", json.dumps(response.data))

    @patch("dcc.issue_draft_views.JiraConnector")
    def test_saved_required_field_makes_preflight_ready(self, connector_class):
        """Supported live requirements can be completed inside the reviewed draft."""

        draft = self.create_draft()
        self.grant_publish_permission()
        payload = draft_update_payload(draft, summary=draft["summary"])
        payload["extra_fields"] = {"customfield_10001": "100"}
        updated = self.client.patch(
            f"/dcc/issue-drafts/{draft['id']}/", payload, format="json"
        ).data
        connector_class.return_value.get_create_fields.return_value = create_metadata()

        response = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/preflight/",
            {"JSESSIONID": "session-credential"},
        )

        self.assertTrue(response.data["ready"])
        self.assertEqual(updated["extra_fields"], {"customfield_10001": "100"})

    def test_nested_extra_field_values_are_rejected(self):
        """Draft edits cannot smuggle nested create payload objects."""

        draft = self.create_draft()
        payload = draft_update_payload(draft, summary=draft["summary"])
        payload["extra_fields"] = {"customfield_10001": {"id": "100"}}

        response = self.client.patch(
            f"/dcc/issue-drafts/{draft['id']}/", payload, format="json"
        )

        self.assertEqual(response.status_code, 400)

    @patch("dcc.issue_draft_services.publish_to_jira")
    def test_preflight_block_restores_approval_without_marking_external_failure(self, publisher):
        """A no-write contract blocker remains approved and correctable."""

        result = {
            "missing_fields": [{"id": "customfield_10001", "name": "Safety level"}],
            "invalid_fields": [], "unsupported_fields": [],
        }
        publisher.side_effect = JiraDraftPreflightBlocked(result)
        draft = self.approved_draft_with_permission()

        response = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/publish/",
            {"version": draft["version"], "JSESSIONID": "session-credential"},
        )

        persisted = JiraIssueDraft.objects.get(pk=draft["id"])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["code"], "JIRA_DRAFT_PREFLIGHT_BLOCKED")
        self.assertEqual(persisted.status, JiraIssueDraftStatus.APPROVED)
        self.assertEqual(persisted.last_error_code, "JIRA_DRAFT_PREFLIGHT_BLOCKED")

    def create_draft(self):
        """Create the fixture draft through its public endpoint."""

        return self.client.post("/dcc/issue-drafts/", {"source_job_id": self.job.id}).data

    def approved_draft_with_permission(self):
        """Return an approved fixture and grant its dedicated publish permission."""

        draft = self.create_draft()
        self.grant_publish_permission()
        response = self.client.post(
            f"/dcc/issue-drafts/{draft['id']}/approve/", {"version": draft["version"]}
        )
        return response.data

    def grant_publish_permission(self):
        """Grant and refresh the dedicated JIRA publication permission."""

        self.user.user_permissions.add(Permission.objects.get(codename="publish_jiraissuedraft"))
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)


class JiraIssueDraftPublisherTests(TestCase):
    """Verify marker-based recovery before any external create request."""

    @patch("dcc.issue_draft_publisher.JiraConnector")
    def test_existing_marker_reuses_issue_without_create(self, connector_class):
        """A timed-out prior create is recovered instead of duplicated."""

        client = connector_class.return_value
        client.find_issue_by_label.return_value = SimpleNamespace(key="CHN-44")
        draft = SimpleNamespace(marker_label="aw-center-safe", project_key="CHN")

        issue_key = publish_to_jira(draft, "session-credential")

        self.assertEqual(issue_key, "CHN-44")
        client.create_issue.assert_not_called()

    @patch("dcc.issue_draft_publisher.JiraConnector")
    def test_live_required_values_are_encoded_before_create(self, connector_class):
        """Only validated live field identifiers reach the JIRA create payload."""

        client = connector_class.return_value
        client.find_issue_by_label.return_value = None
        client.get_create_fields.return_value = create_metadata()
        client.create_issue.return_value = SimpleNamespace(key="CHN-45")
        draft = SimpleNamespace(
            marker_label="aw-center-safe", project_key="CHN", summary="Review",
            description="Evidence", extra_fields={"customfield_10001": "100"},
        )

        issue_key = publish_to_jira(draft, "session-credential")

        self.assertEqual(issue_key, "CHN-45")
        fields = client.create_issue.call_args.args[0]
        self.assertEqual(fields["customfield_10001"], {"id": "100"})
        self.assertEqual(fields["labels"][0], "aw-center-safe")


def create_analysis_job(owner):
    """Persist a deterministic successful private analysis artifact."""

    payload = json.dumps({
        "document": "review.docx",
        "checks": [{
            "id": "approvals", "title": "Approval information", "score": 0.4,
            "status": "error", "explanation": "Approval section is weak.",
            "evidence": [{"text": "Approval evidence", "heading": "Approvals"}],
        }],
    }).encode()
    job = Job.objects.create(
        owner=owner, kind="word.analyze", title="Analyze", status=JobStatus.SUCCEEDED,
        input_name="review.docx", input_sha256="1" * 64, output_name="analysis.json",
        output_sha256=hashlib.sha256(payload).hexdigest(),
    )
    job.output_file.save("analysis.json", ContentFile(payload), save=True)
    return job


def draft_update_payload(draft, summary):
    """Return a complete edit contract based on the current server version."""

    return {
        "project_key": draft["project_key"], "summary": summary,
        "description": draft["description"], "extra_fields": draft.get("extra_fields", {}),
        "version": draft["version"],
    }


def create_metadata():
    """Return deterministic Task create metadata with one required option."""

    base = [
        {"id": identifier, "name": identifier.title(), "required": True,
         "schema": {"type": "string"}, "allowedValues": []}
        for identifier in ("summary", "description", "labels")
    ]
    base.append({
        "id": "customfield_10001", "name": "Safety level", "required": True,
        "hasDefaultValue": False, "schema": {"type": "option"},
        "allowedValues": [{"id": "100", "value": "High"}],
    })
    return base
