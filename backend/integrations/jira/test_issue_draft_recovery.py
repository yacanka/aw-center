"""Executor tests for fenced marker reconciliation and sanitized failures."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from integrations.jira.sessions import JiraSessionNotConnected, JiraSessionRecord
from jobs.contracts import JobExecutionFailure
from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from jobs.worker import claim_next_job, execute_claimed_job
from orgs.models import Project, ProjectRoleAssignment

from integrations.jira.issue_draft_models import JiraIssueDraft, JiraIssueDraftStatus
from integrations.jira.publication_executor import execute_jira_draft_publication
from integrations.jira.test_issue_drafts import create_analysis_job


class JiraDraftPublicationExecutorTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.get(slug="hys")
        self.assignment = ProjectRoleAssignment.objects.create(
            user=self.user,
            project=self.project,
            domain=ProjectRoleAssignment.Domain.JIRA,
            role=ProjectRoleAssignment.Role.PUBLISHER,
        )
        self.source_job = create_analysis_job(self.user)

    def queued_publication(self, key="executor-publication-1"):
        created = self.client.post(
            "/api/integrations/jira/issue-drafts/",
            {
                "source_job_id": str(self.source_job.id),
                "project_key": "CHN",
                "project_slugs": [self.project.slug],
            },
            format="json",
        ).data
        approved = self.client.post(
            f"/api/integrations/jira/issue-drafts/{created['id']}/approve/",
            {"version": created["version"]},
            format="json",
        ).data
        queued = self.client.post(
            f"/api/integrations/jira/issue-drafts/{created['id']}/publish/",
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(queued.status_code, 201)
        return Job.objects.get(pk=queued.data["id"]), created["id"]

    def test_expired_session_is_nonretryable_and_requests_reconnect(self):
        job, draft_id = self.queued_publication()

        with patch(
            "integrations.jira.publication_executor.jira_connector_for",
            side_effect=JiraSessionNotConnected(),
        ):
            with self.assertRaises(JobExecutionFailure) as raised:
                execute_jira_draft_publication(job)

        draft = JiraIssueDraft.objects.get(pk=draft_id)
        self.assertEqual(raised.exception.code, "JIRA_RECONNECT_REQUIRED")
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(draft.status, JiraIssueDraftStatus.FAILED)
        self.assertEqual(draft.last_error_code, "JIRA_RECONNECT_REQUIRED")

    def test_worker_rechecks_publisher_role_before_provider_access(self):
        job, draft_id = self.queued_publication()
        self.assignment.role = ProjectRoleAssignment.Role.VIEWER
        self.assignment.save()

        with patch("integrations.jira.publication_executor.jira_connector_for") as connector_for:
            with self.assertRaises(JobExecutionFailure) as raised:
                execute_jira_draft_publication(job)

        self.assertEqual(raised.exception.code, "DCC_PROJECT_ROLE_REQUIRED")
        connector_for.assert_not_called()
        self.assertEqual(
            JiraIssueDraft.objects.get(pk=draft_id).status,
            JiraIssueDraftStatus.FAILED,
        )

    def test_existing_provider_marker_completes_without_create(self):
        job, draft_id = self.queued_publication()
        connector = Mock()
        connector.find_issue_by_label.return_value = SimpleNamespace(key="CHN-501")

        with (
            patch("integrations.jira.publication_executor.jira_connector_for", return_value=connector),
            patch("integrations.jira.publication_executor.require_jira_session"),
        ):
            result = execute_jira_draft_publication(job)

        draft = JiraIssueDraft.objects.get(pk=draft_id)
        self.assertEqual(draft.status, JiraIssueDraftStatus.PUBLISHED)
        self.assertEqual(draft.jira_issue_key, "CHN-501")
        connector.create_issue.assert_not_called()
        self.assertEqual(result.summary["jira_issue_key"], "CHN-501")
        result.path.unlink(missing_ok=True)

        with patch("integrations.jira.publication_executor.jira_connector_for") as connector_for:
            replay_result = execute_jira_draft_publication(job)
        connector_for.assert_not_called()
        self.assertEqual(replay_result.summary["jira_issue_key"], "CHN-501")
        replay_result.path.unlink(missing_ok=True)

    def test_session_expiry_between_provider_calls_stops_before_create(self):
        job, draft_id = self.queued_publication()
        connector = ready_connector()
        session = JiraSessionRecord("encrypted-in-cache", {}, "2026-08-29T00:00:00Z")

        with (
            patch("integrations.jira.publication_executor.jira_connector_for", return_value=connector),
            patch(
                "integrations.jira.publication_executor.require_jira_session",
                side_effect=[session, JiraSessionNotConnected()],
            ),
        ):
            with self.assertRaises(JobExecutionFailure) as raised:
                execute_jira_draft_publication(job)

        self.assertEqual(raised.exception.code, "JIRA_RECONNECT_REQUIRED")
        connector.create_issue.assert_not_called()
        self.assertEqual(
            JiraIssueDraft.objects.get(pk=draft_id).status,
            JiraIssueDraftStatus.FAILED,
        )

    def test_job_reconciliation_terminal_repairs_stuck_publishing_draft(self):
        job, draft_id = self.queued_publication()

        job.status = JobStatus.RECONCILIATION_REQUIRED
        job.error_code = "JOB_TIMEOUT"
        job.message = "Confirm provider state."
        job.save(update_fields=["status", "error_code", "message", "updated_at"])

        draft = JiraIssueDraft.objects.get(pk=draft_id)
        self.assertEqual(draft.status, JiraIssueDraftStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(draft.last_error_code, "JOB_TIMEOUT")

    def test_job_failure_terminal_repairs_stuck_publishing_draft(self):
        job, draft_id = self.queued_publication()

        job.status = JobStatus.FAILED
        job.error_code = "JIRA_DRAFT_PREFLIGHT_BLOCKED"
        job.message = "Complete required fields."
        job.save(update_fields=["status", "error_code", "message", "updated_at"])

        self.assertEqual(
            JiraIssueDraft.objects.get(pk=draft_id).status,
            JiraIssueDraftStatus.FAILED,
        )

    def test_reconciliation_startup_failure_preserves_prior_uncertainty(self):
        job, draft_id = self.queued_publication()
        job.parameters["mode"] = "reconcile"
        job.status = JobStatus.FAILED
        job.error_code = "JOB_EXECUTOR_START_FAILED"
        job.save(update_fields=["parameters", "status", "error_code", "updated_at"])

        self.assertEqual(
            JiraIssueDraft.objects.get(pk=draft_id).status,
            JiraIssueDraftStatus.RECONCILIATION_REQUIRED,
        )

    def test_uncertain_create_requires_explicit_marker_reconciliation(self):
        job, draft_id = self.queued_publication()
        connector = ready_connector()
        connector.create_issue.side_effect = TimeoutError("private upstream detail")

        with (
            patch("integrations.jira.publication_executor.jira_connector_for", return_value=connector),
            patch("integrations.jira.publication_executor.require_jira_session"),
        ):
            execute_claimed_job(
                claim_next_job("draft-publication-worker", [job.kind]),
                lambda _kind: execute_jira_draft_publication,
            )

        job.refresh_from_db()
        draft = JiraIssueDraft.objects.get(pk=draft_id)
        self.assertEqual(
            draft.last_error_code,
            "JIRA_PUBLICATION_RECONCILIATION_REQUIRED",
        )
        self.assertNotIn("private upstream detail", job.message)
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(draft.status, JiraIssueDraftStatus.RECONCILIATION_REQUIRED)
        self.assertFalse(job.retryable)

        reconciliation = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version, "reconcile": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="executor-reconciliation-2",
        )
        self.assertEqual(reconciliation.status_code, 201)
        reconciliation_job = Job.objects.get(pk=reconciliation.data["id"])
        connector.find_issue_by_label.return_value = SimpleNamespace(key="CHN-777")
        connector.create_issue.reset_mock()

        with (
            patch("integrations.jira.publication_executor.jira_connector_for", return_value=connector),
            patch("integrations.jira.publication_executor.require_jira_session"),
        ):
            result = execute_jira_draft_publication(reconciliation_job)

        draft.refresh_from_db()
        self.assertEqual(draft.status, JiraIssueDraftStatus.PUBLISHED)
        self.assertEqual(draft.jira_issue_key, "CHN-777")
        connector.create_issue.assert_not_called()
        self.assertTrue(result.summary["marker_reused"])
        result.path.unlink(missing_ok=True)

    def test_reconciliation_lookup_failure_stays_uncertain_after_worker_completion(self):
        source, draft_id = self.queued_publication()
        source.status = JobStatus.RECONCILIATION_REQUIRED
        source.save(update_fields=["status"])
        draft = JiraIssueDraft.objects.get(pk=draft_id)
        response = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version, "reconcile": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="reconciliation-lookup-failure",
        )
        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        connector = ready_connector()
        connector.find_issue_by_label.side_effect = TimeoutError("private lookup detail")

        with (
            patch("integrations.jira.publication_executor.jira_connector_for", return_value=connector),
            patch("integrations.jira.publication_executor.require_jira_session"),
        ):
            execute_claimed_job(
                claim_next_job("draft-reconciliation-worker", [job.kind]),
                lambda _kind: execute_jira_draft_publication,
            )

        job.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(draft.status, JiraIssueDraftStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(draft.last_error_code, "JIRA_RECONCILIATION_LOOKUP_FAILED")
        self.assertFalse(job.retryable)
        self.assertNotIn("private lookup detail", job.message)

    def test_reconciliation_session_failure_cannot_enable_fresh_publication(self):
        source, draft_id = self.queued_publication()
        source.status = JobStatus.RECONCILIATION_REQUIRED
        source.save(update_fields=["status"])
        draft = JiraIssueDraft.objects.get(pk=draft_id)
        response = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version, "reconcile": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="reconciliation-session-failure",
        )
        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])

        with patch(
            "integrations.jira.publication_executor.jira_connector_for",
            side_effect=JiraSessionNotConnected(),
        ):
            execute_claimed_job(
                claim_next_job("draft-reconnect-worker", [job.kind]),
                lambda _kind: execute_jira_draft_publication,
            )

        job.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(draft.status, JiraIssueDraftStatus.RECONCILIATION_REQUIRED)
        rejected = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="unsafe-republication-after-session-failure",
        )
        self.assertEqual(rejected.status_code, 409)

    def test_completed_reconciliation_without_marker_allows_fresh_publication(self):
        source, draft_id = self.queued_publication()
        source.status = JobStatus.RECONCILIATION_REQUIRED
        source.save(update_fields=["status"])
        draft = JiraIssueDraft.objects.get(pk=draft_id)
        response = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version, "reconcile": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="reconciliation-marker-absent",
        )
        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])
        connector = ready_connector()

        with (
            patch("integrations.jira.publication_executor.jira_connector_for", return_value=connector),
            patch("integrations.jira.publication_executor.require_jira_session"),
        ):
            execute_claimed_job(
                claim_next_job("draft-marker-absent-worker", [job.kind]),
                lambda _kind: execute_jira_draft_publication,
            )

        job.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(draft.status, JiraIssueDraftStatus.FAILED)
        self.assertEqual(draft.last_error_code, "JIRA_RECONCILIATION_NOT_FOUND")
        connector.create_issue.assert_not_called()
        retry = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="confirmed-safe-publication-retry",
        )
        self.assertEqual(retry.status_code, 201)

    def test_cancelled_queued_reconciliation_cannot_enable_fresh_publication(self):
        source, draft_id = self.queued_publication()
        source.status = JobStatus.RECONCILIATION_REQUIRED
        source.save(update_fields=["status"])
        draft = JiraIssueDraft.objects.get(pk=draft_id)
        response = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version, "reconcile": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="cancel-queued-reconciliation",
        )
        self.assertEqual(response.status_code, 201)
        job = Job.objects.get(pk=response.data["id"])

        cancelled = self.client.post(f"/api/jobs/{job.id}/cancel/")

        self.assertEqual(cancelled.status_code, 200)
        job.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(job.status, JobStatus.CANCELLED)
        self.assertEqual(draft.status, JiraIssueDraftStatus.RECONCILIATION_REQUIRED)
        rejected = self.client.post(
            f"/api/integrations/jira/issue-drafts/{draft_id}/publish/",
            {"version": draft.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="unsafe-republication-after-cancellation",
        )
        self.assertEqual(rejected.status_code, 409)


def ready_connector():
    connector = Mock()
    connector.find_issue_by_label.return_value = None
    connector.get_create_fields.return_value = [
        {
            "id": identifier,
            "name": identifier.title(),
            "required": True,
            "schema": {"type": "string"},
            "allowedValues": [],
        }
        for identifier in ("summary", "description", "labels")
    ]
    return connector
