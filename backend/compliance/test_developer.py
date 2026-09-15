"""Development reset authorization, atomicity and scope regressions."""
from unittest.mock import patch
from datetime import timedelta
import uuid

from django.utils import timezone
from jobs.models import Job, JobStatus

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from orgs.models import Panel, Person, Project, ProjectRoleAssignment, ResponsibleAssignment
from .developer import RESET_PHRASE
from .models import ComplianceDocument, CoverPage, CoverPageNumberAllocation, DeveloperResetState
from .reset_guard import ResetInProgress
from .numbering import resume_allocation
from .notifications import scan_notifications


@override_settings(DEBUG=True, AWCENTER_DEPLOYMENT_MODE="development")
class DeveloperResetTests(TestCase):
    url = "/api/developer/compliance-organization-reset/"

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("reset-admin", password="test-only")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.project = Project.objects.get(slug="ozgur")
        self.panel = Panel.objects.create(project=self.project, name="Panel", ata="27-00")
        self.person = Person.objects.create(person_id="test-person", name="Test", email="test@example.invalid")
        ResponsibleAssignment.objects.create(panel=self.panel, person=self.person, responsibility_role="AS")
        self.cover = CoverPage.objects.create(project=self.project, number="CP-TEST")
        self.document = ComplianceDocument.objects.create(project=self.project, panel=self.panel, cover_page=self.cover, name="Test")

    def payload(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(self.url, {
            "action": "prepare", "confirmation_token": response.data["confirmation_token"],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return {"confirmation_phrase": RESET_PHRASE, "confirmation_token": response.data["confirmation_token"]}

    def test_reset_clears_protected_relations_and_history_preserving_catalog_accounts_and_dcc_roles(self):
        ProjectRoleAssignment.objects.create(project=self.project, user=self.user, domain="dcc", role="viewer")
        ProjectRoleAssignment.objects.create(project=self.project, user=self.user, domain="compliance", role="manager")
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        for model in [ComplianceDocument, CoverPage, Panel, Person, ResponsibleAssignment]:
            self.assertFalse(model.objects.exists(), model.__name__)
        self.assertFalse(ComplianceDocument.history.exists())
        self.assertFalse(CoverPage.history.exists())
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertEqual(list(ProjectRoleAssignment.objects.values_list("domain", flat=True)), ["dcc"])

    @override_settings(DEBUG=False)
    def test_production_is_disabled_for_superuser(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 404)
        self.assertTrue(ComplianceDocument.objects.exists())

    def test_staff_and_anonymous_are_denied(self):
        self.user.is_superuser = False
        self.user.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_confirmation_required_and_stale_preview_rejected(self):
        payload = self.payload()
        self.assertEqual(self.client.post(self.url, {**payload, "confirmation_phrase": "wrong"}, format="json").status_code, 400)
        Person.objects.create(person_id="another", name="Other", email="other@example.invalid")
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertTrue(ComplianceDocument.objects.exists())

    def test_invalid_and_expired_tokens_rejected(self):
        payload = self.payload()
        self.assertEqual(self.client.post(self.url, {**payload, "confirmation_token": "invalid"}, format="json").status_code, 400)
        with patch("django.core.signing.time.time", return_value=9999999999):
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)

    def job(self, **overrides):
        values = {"owner": self.user, "kind": "compliance.allocate_cover_page_number"}
        return Job.objects.create(**(values | overrides))

    def allocation(self, job, **overrides):
        values = {
            "project": self.project, "actor": self.user, "current_job": job,
            "client_operation_id": uuid.uuid4(), "document_snapshot": {},
        }
        return CoverPageNumberAllocation.objects.create(**(values | overrides))

    def test_running_job_is_cancel_requested_and_blocks_reset(self):
        job = self.job(status=JobStatus.RUNNING, started_at=timezone.now(),
                       lease_expires_at=timezone.now() + timedelta(minutes=5))
        payload = self.payload()
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.CANCEL_REQUESTED)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ComplianceDocument.objects.exists())
        blockers = self.client.get(self.url).data["blockers"]
        self.assertEqual(blockers["job_count"], 1)
        self.assertEqual(blockers["jobs"][0]["id"], job.pk)

    def test_unrelated_active_and_uncertain_jobs_do_not_block_or_get_cancelled(self):
        active = self.job(kind="media.convert", status=JobStatus.RUNNING)
        self.job(kind="teamcenter.set_properties", status=JobStatus.RECONCILIATION_REQUIRED)
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        active.refresh_from_db()
        self.assertEqual(active.status, JobStatus.RUNNING)

    def test_unstarted_cancelled_allocation_can_be_deleted(self):
        job = self.job()
        allocation = self.allocation(job)
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.CANCELLED)
        self.assertFalse(CoverPageNumberAllocation.objects.filter(pk=allocation.pk).exists())
        self.assertFalse(DeveloperResetState.objects.get().active)

    def test_external_evidence_or_previous_attempts_still_block(self):
        for overrides in ({"remote_id": 42}, {"version": 2}):
            with self.subTest(overrides=overrides):
                allocation = self.allocation(self.job(), **overrides)
                response = self.client.post(self.url, self.payload(), format="json")
                self.assertEqual(response.status_code, 400)
                self.assertTrue(CoverPageNumberAllocation.objects.filter(pk=allocation.pk).exists())

    def test_expired_external_write_lease_is_fenced_but_not_forgotten(self):
        token = uuid.uuid4()
        job = self.job(status=JobStatus.RUNNING, started_at=timezone.now(),
                       execution_token=token, reconcile_on_lease_loss=True,
                       lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.allocation(job)
        payload = self.payload()
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.RECONCILIATION_REQUIRED)
        self.assertIsNone(job.execution_token)
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertEqual(self.client.get(self.url).data["blockers"]["uncertain_job_count"], 1)

    def test_preparation_blocks_writes_and_release_invalidates_old_preview(self):
        payload = self.payload()
        url = f"/api/projects/{self.project.slug}/compliance-documents/"
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"] if hasattr(response, "data") else response.json()["code"],
                         "COMPLIANCE_RESET_IN_PROGRESS")
        self.assertEqual(self.client.get(url).status_code, 200)
        release = self.client.post(self.url, {**payload, "action": "release"}, format="json")
        self.assertEqual(release.status_code, 200)
        self.assertFalse(release.data["prepared"])
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertNotEqual(self.client.post(url, {}, format="json").status_code, 409)

    def test_preparation_blocks_service_resume_and_pauses_notification_scan(self):
        allocation = self.allocation(self.job())
        self.payload()
        with self.assertRaises(ResetInProgress):
            resume_allocation(allocation=allocation, expected_version=1)
        with patch("compliance.notifications._prepare_scan") as scan:
            self.assertEqual(scan_notifications()["processed"], 0)
        scan.assert_not_called()

    def test_reset_requires_preparation(self):
        preview = self.client.get(self.url).data
        self.assertFalse(preview["ready"])
        response = self.client.post(self.url, {
            "confirmation_token": preview["confirmation_token"],
            "confirmation_phrase": RESET_PHRASE,
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_session_post_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload(), format="json").status_code, 403)

    @override_settings(AWCENTER_DEPLOYMENT_MODE="windows-native")
    def test_production_profile_is_disabled_even_with_debug(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_preview_is_bound_to_user(self):
        payload = self.payload()
        other = get_user_model().objects.create_superuser("other-admin")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 403)
        self.assertTrue(ComplianceDocument.objects.exists())

    def test_protected_dependency_rolls_back_prior_deletions(self):
        from django.db.models.query import QuerySet
        original_delete = QuerySet.delete

        def delete(queryset):
            if queryset.model is Person:
                raise ProtectedError("Test dependency", [self.person])
            return original_delete(queryset)

        payload = self.payload()
        with patch.object(QuerySet, "delete", delete):
            response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ComplianceDocument.objects.filter(pk=self.document.pk).exists())
        self.assertTrue(CoverPage.objects.filter(pk=self.cover.pk).exists())
        self.assertTrue(ResponsibleAssignment.objects.exists())

    def test_claimed_notification_blocks_reset_until_delivery_finishes(self):
        from .models import NotificationLog, TrackingProfile

        profile = TrackingProfile.objects.create(document=self.document)
        log = NotificationLog.objects.create(
            profile=profile, event_type="overdue", event_key="reset-test-notification",
            message_id="<reset-test@example.invalid>", status=NotificationLog.Status.CLAIMED,
        )
        payload = self.payload()
        self.assertEqual(self.client.get(self.url).data["blockers"]["notification_count"], 1)
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        log.status = NotificationLog.Status.SENT
        log.save()
        self.assertEqual(self.client.post(self.url, self.payload(), format="json").status_code, 200)

    def test_successful_resume_does_not_leave_old_uncertain_job_as_a_blocker(self):
        allocation_id = uuid.uuid4()
        self.job(status=JobStatus.RECONCILIATION_REQUIRED,
                 parameters={"allocation_id": str(allocation_id)})
        self.allocation(self.job(status=JobStatus.SUCCEEDED), id=allocation_id,
                        status=CoverPageNumberAllocation.Status.COMPLETED)
        self.assertEqual(self.client.post(self.url, self.payload(), format="json").status_code, 200)

    def test_organization_and_admin_writes_are_paused(self):
        self.payload()
        for url in (
            f"/api/projects/{self.project.slug}/organization/people/",
            "/admin/compliance/compliancedocument/add/",
            "/admin/orgs/person/add/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}, format="json").status_code, 409)
