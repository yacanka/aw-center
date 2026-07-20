"""Regression tests for credential-free stale DCC source refresh previews."""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.utils import timezone

from jobs.confirmation import create_confirmation_job
from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from projects.ozgur.models import CompDoc

from .compdoc_bridge import attach_compliance_documents
from .compdoc_preview_revision import snapshot_upload
from .job_parameters import build_preview_parameters
from .models import DccCompdocTrace


class CompdocRefreshPreviewTests(JobTestCase):
    """Verify refresh authorization, lineage, idempotency, and source-state safety."""

    def setUp(self):
        """Create an authorized DCC owner and one traced source document."""

        super().setUp()
        self.document = CompDoc.objects.create(
            name="Original Manual", cover_page_no="REFRESH-1", tech_doc_no="TD-1"
        )
        self.permissions = [
            permission("dcc", "add_jira_dcc"),
            permission("dcc", "view_jira_dcc"),
            permission("ozgur", "view_compdoc"),
        ]
        self.user.user_permissions.add(*self.permissions)
        self.source, self.trace = create_source(self.user, self.document)

    @patch("dcc.compdoc_refresh.prepare_dcc_preview")
    def test_refresh_rebuilds_current_sources_and_replays_semantically(self, prepare):
        """One click creates one current preview without mutating or recapturing JIRA."""

        prepare.return_value = preview_summary()
        self.change_document("Current Manual")
        created = self.refresh("refresh-current-source")
        replayed = self.refresh("different-key-same-trace")
        child = Job.objects.get(pk=created.data["id"])

        self.assertEqual(created.status_code, 201)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(replayed.data["id"], created.data["id"])
        self.assertEqual(child.status, JobStatus.AWAITING_CONFIRMATION)
        self.assertEqual(child.source_job_id, self.source.id)
        self.assertEqual(self.source.status, JobStatus.SUCCEEDED)
        refresh_summary = child.result_summary["compdoc_refresh"]
        self.assertEqual(refresh_summary["source_trace_id"], str(self.trace.id))
        with child.input_file.open("rb") as stored:
            refreshed = json.load(stored)
        refreshed_source = refreshed["compliance_documents"]["documents"][0]
        self.assertEqual(refreshed_source["name"], "Current Manual")
        self.assertNotIn("JSESSIONID", json.dumps(refreshed))
        self.assertTrue(child.events.filter(code="DCC_COMPDOC_REFRESH_DERIVED").exists())
        confirmed = self.client.post(f"/dcc/jobs/create-document/{child.id}/confirm/", {})
        self.assertEqual(confirmed.data["status"], JobStatus.QUEUED)
        self.assertTrue(DccCompdocTrace.objects.filter(job_id=child.id).exists())

    def test_non_dcc_metadata_change_does_not_create_preview(self):
        """A notes-only history advance is explicitly a no-op for regenerated output."""

        self.document.notes = "Internal note"
        self.document.save(update_fields=["notes"])

        response = self.refresh("refresh-not-required")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "DCC_COMPDOC_REFRESH_NOT_REQUIRED")
        self.assertEqual(Job.objects.filter(source_job=self.source).count(), 0)

    def test_active_and_archived_sources_return_actionable_states(self):
        """An active source waits while an archived source requires a new JIRA capture."""

        self.change_document("Changed Manual")
        self.source.status = JobStatus.RUNNING
        self.source.save(update_fields=["status"])
        active = self.refresh("refresh-active")
        self.source.delete()
        archived = self.refresh("refresh-archived")

        self.assertEqual(active.status_code, 409)
        self.assertEqual(active.data["code"], "DCC_COMPDOC_REFRESH_SOURCE_ACTIVE")
        self.assertEqual(archived.status_code, 410)
        self.assertEqual(archived.data["code"], "DCC_COMPDOC_REFRESH_SOURCE_ARCHIVED")

    def test_cross_owner_and_revoked_project_access_fail_closed(self):
        """Neither another creator nor an owner without current project access can refresh."""

        self.change_document("Permission-sensitive Manual")
        self.other_user.user_permissions.add(*self.permissions)
        self.client.force_authenticate(self.other_user)
        hidden = self.refresh("refresh-other-owner")
        self.user.user_permissions.remove(permission("ozgur", "view_compdoc"))
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)
        revoked = self.refresh("refresh-revoked")

        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(revoked.status_code, 403)
        self.assertFalse(Job.objects.filter(source_job=self.source).exists())

    def test_trace_api_exposes_owner_safe_refresh_capability(self):
        """Reverse provenance reports readiness only after a DCC-visible source change."""

        current = self.trace_page()["results"][0]
        self.change_document("Refresh-ready Manual")
        changed = self.trace_page()["results"][0]
        self.source.delete()
        archived = self.trace_page()["results"][0]

        self.assertEqual(current["refresh_status"], "current")
        self.assertEqual(changed["refresh_status"], "ready")
        self.assertTrue(changed["can_refresh_preview"])
        self.assertEqual(archived["refresh_status"], "source_archived")

    def refresh(self, key):
        """Request a refresh preview for the representative trace."""

        return self.client.post(
            f"/dcc/compdoc-traceability/{self.trace.id}/refresh-preview/",
            {}, format="json", HTTP_IDEMPOTENCY_KEY=key,
        )

    def trace_page(self):
        """Return the permission-scoped reverse trace payload."""

        return self.client.get(
            "/dcc/compdoc-traceability/",
            {"project": "ozgur", "compdoc_id": str(self.document.pk)},
        ).data

    def change_document(self, name):
        """Advance one DCC-visible source field."""

        self.document.name = name
        self.document.save(update_fields=["name"])


def create_source(owner, document):
    """Persist one terminal DCC job and its matching immutable trace."""

    snapshot = attach_compliance_documents(
        source_snapshot(), owner, "ozgur", [str(document.pk)]
    )
    parameters = build_preview_parameters("DCC-REFRESH-1", "ozgur", [str(document.pk)])
    job, _created = create_confirmation_job(
        owner, "dcc.create_document", "Original DCC", parameters,
        snapshot_upload(snapshot), timezone.now() + timedelta(minutes=15),
        preview_summary(), "original-refresh-source",
    )
    job.status = JobStatus.SUCCEEDED
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "completed_at"])
    bundle = snapshot["compliance_documents"]
    source = bundle["documents"][0]
    trace = DccCompdocTrace.objects.create(
        job_id=job.id, job_input_sha256=job.input_sha256, confirmed_by=owner,
        issue_key="DCC-REFRESH-1", project_slug="ozgur", compdoc_id=document.pk,
        source_history_id=source["source_history_id"],
        source_history_at=source["source_history_at"],
        snapshot_fingerprint=bundle["fingerprint"],
    )
    return job, trace


def source_snapshot():
    """Return a valid private JIRA snapshot without transient credentials."""

    return {
        "schema_version": 1, "issue_key": "DCC-REFRESH-1", "project_slug": "ozgur",
        "project_label": "Ozgur", "output_name": "refresh.docx", "panel_count": 0,
        "placeholders": {"Design_Change_Title": "Refresh source"},
    }


def preview_summary():
    """Return a minimal confirmation-compatible DCC preview summary."""

    return {
        "type": "dcc_preview", "readiness_warning_codes": [],
        "requires_readiness_acknowledgement": False,
    }


def permission(app_label, codename):
    """Resolve one exact model permission fixture."""

    return Permission.objects.get(content_type__app_label=app_label, codename=codename)
