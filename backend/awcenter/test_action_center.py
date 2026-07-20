from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.models import CompDocImportAudit
from dcc.issue_draft_models import JiraIssueDraft, JiraIssueDraftStatus
from jobs.models import Job, JobStatus
from users.models import UserInvitation

User = get_user_model()


class ActionCenterTests(TestCase):
    """Verify permission-aware cross-workflow attention prioritization."""

    def setUp(self):
        """Create two users and an authenticated API client."""

        self.user = User.objects.create_user("action-user", password="StrongPass!123")
        self.other = User.objects.create_user("other-user", password="StrongPass!123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_jobs_are_owner_scoped_and_retried_failures_are_resolved(self):
        """The queue excludes other owners and failures with a retry attempt."""

        visible = create_failed_job(self.user, "Visible failure")
        create_failed_job(self.other, "Private failure")
        retried = create_failed_job(self.user, "Already retried")
        create_job(self.user, "Retry attempt", JobStatus.SUCCEEDED, retry_of=retried)

        response = self.client.get("/action-center/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"], {"total": 1, "critical": 1, "warning": 0})
        self.assertEqual(response.data["items"][0]["id"], f"job:{visible.pk}")
        self.assertNotIn("input_file", str(response.data))

    def test_imports_require_permission_and_critical_items_rank_first(self):
        """Audit signals obey model permission and deterministic severity ranking."""

        create_failed_job(self.user, "Critical job")
        audit = create_partial_audit()
        denied = self.client.get("/action-center/")
        self.user.user_permissions.add(
            Permission.objects.get(codename="view_compdocimportaudit")
        )
        self.reload_authenticated_user()
        allowed = self.client.get("/action-center/")

        self.assertEqual([item["kind"] for item in denied.data["items"]], ["job"])
        self.assertEqual([item["kind"] for item in allowed.data["items"]], ["job", "import"])
        self.assertEqual(allowed.data["items"][1]["id"], f"import:{audit.pk}")
        self.assertIn(f"audit={audit.pk}", allowed.data["items"][1]["action_path"])

    def test_only_invitation_managers_see_links_approaching_expiry(self):
        """Invitation warnings mirror the staff and add-user permission boundary."""

        invitation = create_expiring_invitation(self.user)
        denied = self.client.get("/action-center/")
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.user.user_permissions.add(Permission.objects.get(codename="add_user"))
        self.reload_authenticated_user()
        allowed = self.client.get("/action-center/")

        self.assertEqual(denied.data["summary"]["total"], 0)
        self.assertEqual(allowed.data["items"][0]["id"], f"invitation:{invitation.pk}")
        self.assertEqual(allowed.data["items"][0]["action_path"], "/users?invitations=active")
        self.assertNotIn(invitation.token_digest, str(allowed.data))

    def test_unresolved_jira_drafts_are_owner_scoped_and_actionable(self):
        """Approved and failed bridge drafts return their owner to the source analysis."""

        source = create_job(self.user, "Analysis", JobStatus.SUCCEEDED)
        draft = create_jira_draft(self.user, source, JiraIssueDraftStatus.FAILED)
        other_source = create_job(self.other, "Private analysis", JobStatus.SUCCEEDED)
        create_jira_draft(self.other, other_source, JiraIssueDraftStatus.APPROVED)

        response = self.client.get("/action-center/")

        self.assertEqual(response.data["summary"], {"total": 1, "critical": 1, "warning": 0})
        self.assertEqual(response.data["items"][0]["id"], f"jira-draft:{draft.pk}")
        self.assertEqual(response.data["items"][0]["action_path"], f"/jobs?job={source.pk}")
        self.assertNotIn("description", str(response.data))

    def test_all_sources_are_loaded_with_bounded_queries(self):
        """Cross-domain aggregation and trace discovery avoid per-item query growth."""

        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        create_failed_job(self.user, "Failed operation")
        create_partial_audit()
        create_expiring_invitation(self.user)

        with self.assertNumQueries(6):
            response = self.client.get("/action-center/")

        self.assertEqual(response.data["summary"]["total"], 3)

    def reload_authenticated_user(self):
        """Mirror a new request user after changing permissions in a test."""

        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)


def create_failed_job(owner, title):
    """Create one retryable failed background job."""

    return create_job(owner, title, JobStatus.FAILED, error_code="JOB_TIMEOUT")


def create_job(owner, title, status, **values):
    """Create a minimal durable job without writing a test artifact."""

    return Job.objects.create(
        owner=owner,
        kind="test_operation",
        title=title,
        status=status,
        input_file="jobs/test/input.txt",
        input_name="input.txt",
        input_sha256="a" * 64,
        **values,
    )


def create_partial_audit():
    """Create one recent import audit requiring review."""

    return CompDocImportAudit.objects.create(
        project_slug="ozgur",
        source_filename="compdocs.xlsx",
        source_sha256="b" * 64,
        imported_by_username="importer",
        total_rows=4,
        created_count=3,
        rejected_count=1,
        status=CompDocImportAudit.Status.PARTIAL,
    )


def create_expiring_invitation(creator):
    """Create one active invitation inside the six-hour warning window."""

    return UserInvitation.objects.create(
        token_digest="c" * 64,
        email="recipient@example.com",
        created_by=creator,
        expires_at=timezone.now() + timedelta(hours=2),
    )


def create_jira_draft(owner, source_job, status):
    """Create one minimal unresolved bridge draft without private report content."""

    return JiraIssueDraft.objects.create(
        owner=owner, source_job=source_job, project_key="CHN", summary="Review analysis",
        description="Private findings", status=status, marker_label=f"aw-center-{source_job.pk.hex}",
        approved_at=timezone.now(), last_error_code="JIRA_DRAFT_PUBLISH_FAILED",
    )
