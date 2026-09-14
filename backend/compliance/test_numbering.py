"""Acceptance tests for Numarator-backed cover page allocation."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from awcenter.job_executors import resolve_job_executor
from integrations.numarator.client import GeneratedNumber
from jobs.models import Job, JobStatus
from jobs.worker import claim_next_job, execute_claimed_job
from orgs.models import Panel, Project, ProjectRoleAssignment

from .models import ComplianceDocument, CoverPage, CoverPageNumberAllocation, ReviewTask


NUMARATOR_SETTINGS = {
    "NUMARATOR_ENABLED": True,
    "NUMARATOR_BASE_URL": "https://numarator.example.test",
    "NUMARATOR_API_KEY": "dnk_test_secret",
    "NUMARATOR_CREDENTIAL_ID": "test-v1",
    "NUMARATOR_PROJECT_FORMATS": {"ozgur": "COVER_PAGE"},
}


@override_settings(**NUMARATOR_SETTINGS)
class CoverPageNumberingTests(TestCase):
    def setUp(self):
        self.media_directory = Path(tempfile.mkdtemp())
        self.private_media_override = override_settings(
            PRIVATE_MEDIA_ROOT=self.media_directory / "private"
        )
        self.private_media_override.enable()
        self.project = Project.objects.get(slug="ozgur")
        self.panel = Panel.objects.create(
            project=self.project,
            name="Flight",
            discipline="Systems",
            ata="27-00",
        )
        self.editor = get_user_model().objects.create_user("number-editor")
        self.viewer = get_user_model().objects.create_user("number-viewer")
        for user, role in (
            (self.editor, ProjectRoleAssignment.Role.EDITOR),
            (self.viewer, ProjectRoleAssignment.Role.VIEWER),
        ):
            ProjectRoleAssignment.objects.create(
                project=self.project,
                domain=ProjectRoleAssignment.Domain.COMPLIANCE,
                role=role,
                user=user,
            )
        self.client = APIClient()
        self.client.force_authenticate(self.editor)
        self.url = "/api/projects/ozgur/compliance-documents/number-allocations/"

    def tearDown(self):
        self.private_media_override.disable()
        shutil.rmtree(self.media_directory, ignore_errors=True)

    def payload(self, operation_id=None, *, name="Generated document"):
        return {
            "client_operation_id": str(operation_id or uuid4()),
            "document": {
                "panel": self.panel.pk,
                "cover_page": {"issue": "A"},
                "name": name,
            },
        }

    def test_editor_can_enqueue_idempotently_but_viewer_cannot(self):
        payload = self.payload()

        first = self.client.post(self.url, payload, format="json")
        replay = self.client.post(self.url, payload, format="json")
        self.client.force_authenticate(self.viewer)
        rejected = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(CoverPageNumberAllocation.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 1)

    def test_same_operation_with_different_document_is_rejected(self):
        operation_id = uuid4()
        self.client.post(self.url, self.payload(operation_id), format="json")

        response = self.client.post(
            self.url,
            self.payload(operation_id, name="Different document"),
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "NUMARATOR_ALLOCATION_CONFLICT")

    def test_resume_rejects_a_stale_allocation_version(self):
        response = self.client.post(self.url, self.payload(), format="json")
        allocation = CoverPageNumberAllocation.objects.get(pk=response.data["id"])
        allocation.version = 2
        allocation.save(update_fields=["version", "updated_at"])

        resumed = self.client.post(
            f"{self.url}{allocation.id}/resume/",
            {"version": 1},
            format="json",
        )

        self.assertEqual(resumed.status_code, 409)
        self.assertEqual(resumed.data["code"], "VERSION_CONFLICT")
        self.assertEqual(Job.objects.count(), 1)

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_worker_creates_document_and_marks_number_used(self, client_class):
        client = client_class.return_value
        client.generate_number.return_value = GeneratedNumber(
            41, "CP-2026-0041", "COVER_PAGE", "active", "num-request-1"
        )
        client.mark_used.return_value = GeneratedNumber(
            41, "CP-2026-0041", "COVER_PAGE", "used", "num-request-2"
        )
        response = self.client.post(self.url, self.payload(), format="json")

        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)

        allocation = CoverPageNumberAllocation.objects.get(pk=response.data["id"])
        allocation.current_job.refresh_from_db()
        self.assertEqual(allocation.status, CoverPageNumberAllocation.Status.COMPLETED)
        self.assertEqual(allocation.current_job.status, JobStatus.SUCCEEDED)
        self.assertEqual(allocation.document.cover_page.number, "CP-2026-0041")
        self.assertEqual(ComplianceDocument.objects.count(), 1)
        client.generate_number.assert_called_once()
        client.mark_used.assert_called_once_with(41)

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_worker_rejects_an_allocation_after_project_is_disabled(self, client_class):
        response = self.client.post(self.url, self.payload(), format="json")
        self.project.enabled = False
        self.project.save(update_fields=["enabled"])

        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)

        allocation = CoverPageNumberAllocation.objects.get(pk=response.data["id"])
        allocation.current_job.refresh_from_db()
        self.assertEqual(allocation.current_job.status, JobStatus.FAILED)
        self.assertEqual(allocation.current_job.error_code, "PROJECT_ROLE_REQUIRED")
        self.assertEqual(ComplianceDocument.objects.count(), 0)
        client_class.assert_not_called()

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_worker_assigns_number_to_existing_unnumbered_document(self, client_class):
        cover_page = CoverPage.objects.create(project=self.project, number="", issue="A")
        document = ComplianceDocument.objects.create(
            project=self.project,
            panel=self.panel,
            cover_page=cover_page,
            name="Waiting for a number",
            owner=self.editor,
        )
        review = ReviewTask.objects.create(
            document=document,
            kind=ReviewTask.Kind.REVIEW,
            assignee=self.editor,
            assignee_username=self.editor.username,
            requested_by=self.editor,
            requested_by_username=self.editor.username,
            request_note="Review the unnumbered document.",
            source_version=document.version,
        )
        client = client_class.return_value
        client.generate_number.return_value = GeneratedNumber(
            43, "CP-2026-0043", "COVER_PAGE", "active", "num-request-1"
        )
        client.mark_used.return_value = GeneratedNumber(
            43, "CP-2026-0043", "COVER_PAGE", "used", "num-request-2"
        )
        payload = self.payload(name=document.name)
        payload["document_id"] = str(document.id)

        response = self.client.post(self.url, payload, format="json")
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)

        document.refresh_from_db()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(document.cover_page.number, "CP-2026-0043")
        self.assertEqual(document.version, 2)
        review.refresh_from_db()
        self.assertEqual(review.status, ReviewTask.Status.SUPERSEDED)
        self.assertEqual(ComplianceDocument.objects.count(), 1)

    def test_existing_document_allocation_rejects_archived_or_shared_cover_page(self):
        cover_page = CoverPage.objects.create(project=self.project, number="", issue="A")
        archived = ComplianceDocument.objects.create(
            project=self.project,
            panel=self.panel,
            cover_page=cover_page,
            name="Archived document",
            is_archived=True,
        )
        archived_response = self.client.post(
            self.url,
            {**self.payload(name=archived.name), "document_id": str(archived.pk)},
            format="json",
        )
        archived.is_archived = False
        archived.save(update_fields=["is_archived"])
        ComplianceDocument.objects.create(
            project=self.project,
            panel=self.panel,
            cover_page=cover_page,
            name="Shared-cover document",
        )
        shared_response = self.client.post(
            self.url,
            {**self.payload(name=archived.name), "document_id": str(archived.pk)},
            format="json",
        )

        self.assertEqual(archived_response.status_code, 400)
        self.assertEqual(shared_response.status_code, 400)
        self.assertEqual(CoverPageNumberAllocation.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)

    def test_document_can_be_created_without_cover_page_number(self):
        response = self.client.post(
            "/api/projects/ozgur/compliance-documents/",
            {
                "panel": self.panel.pk,
                "cover_page": {"number": "", "issue": "A"},
                "name": "Number later",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["cover_page"]["number"], "")

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_use_notification_retry_does_not_create_another_document(self, client_class):
        from integrations.numarator.client import NumaratorTemporaryError

        client = client_class.return_value
        client.generate_number.return_value = GeneratedNumber(
            42, "CP-2026-0042", "COVER_PAGE", "active", "num-request-1"
        )
        client.mark_used.side_effect = NumaratorTemporaryError("temporary")
        response = self.client.post(self.url, self.payload(), format="json")
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)
        allocation = CoverPageNumberAllocation.objects.get(pk=response.data["id"])

        self.assertEqual(allocation.status, CoverPageNumberAllocation.Status.USE_PENDING)
        self.assertEqual(ComplianceDocument.objects.count(), 1)
        self.assertEqual(allocation.current_job.status, JobStatus.FAILED)

        client.mark_used.side_effect = None
        client.mark_used.return_value = GeneratedNumber(
            42, "CP-2026-0042", "COVER_PAGE", "used", "num-request-2"
        )
        resumed = self.client.post(
            f"{self.url}{allocation.id}/resume/",
            {"version": allocation.version},
            format="json",
        )
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)

        allocation.refresh_from_db()
        self.assertEqual(resumed.status_code, 202)
        self.assertEqual(allocation.status, CoverPageNumberAllocation.Status.COMPLETED)
        self.assertEqual(ComplianceDocument.objects.count(), 1)
        client.generate_number.assert_called_once()
        self.assertEqual(client.mark_used.call_count, 2)

    def test_options_expose_no_configuration_or_secret_values(self):
        response = self.client.get(
            "/api/projects/ozgur/compliance-documents/numbering-options/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "provider": "numarator",
                "available": True,
                "supports": ["create_document", "assign_existing_document"],
                "formats": ["COVER_PAGE"],
            },
        )
        self.assertNotIn("dnk_", response.content.decode("utf-8"))

    @override_settings(NUMARATOR_PROJECT_FORMATS={"ozgur": ["COVER_PAGE", "CP_ALT"]})
    def test_format_selection_is_required_allowlisted_and_idempotent(self):
        options = self.client.get(self.url.replace("number-allocations", "numbering-options"))
        self.assertEqual(options.data["formats"], ["COVER_PAGE", "CP_ALT"])
        payload = self.payload()
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        payload["format_code"] = "OTHER_PROJECT"
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        payload["format_code"] = "CP_ALT"
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(CoverPageNumberAllocation.objects.get(pk=response.data["id"]).format_code, "CP_ALT")
        payload["format_code"] = "COVER_PAGE"
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 409)
        self.assertEqual(Job.objects.count(), 1)

    def existing_payload(self):
        cover = CoverPage.objects.create(project=self.project, number="", issue="A")
        document = ComplianceDocument.objects.create(
            project=self.project, panel=self.panel, cover_page=cover, name="Unnumbered",
        )
        payload = self.payload(name="Edited before numbering")
        payload["document_id"] = str(document.pk)
        payload["document"]["version"] = document.version
        payload["document"]["notes"] = "Saved with the selected number"
        payload["document"]["cover_page"] = {"issue": "B", "version": cover.version}
        return document, payload

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_existing_allocation_saves_edits_and_replays_after_completion(self, client_class):
        document, payload = self.existing_payload()
        client = client_class.return_value
        client.generate_number.return_value = GeneratedNumber(45, "CP-0045", "COVER_PAGE", "active", "")
        client.mark_used.return_value = GeneratedNumber(45, "CP-0045", "COVER_PAGE", "used", "")
        response = self.client.post(self.url, payload, format="json")
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)
        replay = self.client.post(self.url, payload, format="json")
        document.refresh_from_db()
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["id"], response.data["id"])
        self.assertEqual(document.name, "Edited before numbering")
        self.assertEqual(document.notes, "Saved with the selected number")
        self.assertEqual(document.cover_page.number, "CP-0045")
        self.assertEqual(document.cover_page.issue, "B")
        self.assertEqual(document.version, 2)
        self.assertEqual(document.cover_page.version, 2)
        self.assertEqual(Job.objects.count(), 1)

    def test_existing_allocation_rejects_stale_versions_and_duplicate_operations(self):
        document, payload = self.existing_payload()
        payload["document"]["version"] = 20
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 409)
        payload["document"]["version"] = document.version
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 202)
        payload["client_operation_id"] = str(uuid4())
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 409)
        self.assertEqual(Job.objects.count(), 1)

    def test_unfinished_existing_allocation_can_be_reopened_only_by_its_actor(self):
        document, payload = self.existing_payload()
        created = self.client.post(self.url, payload, format="json")
        restored = self.client.get(self.url, {"document_id": str(document.pk)})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data["allocation"]["id"], created.data["id"])
        self.assertEqual(restored.data["allocation"]["format_code"], "COVER_PAGE")
        other = get_user_model().objects.create_user("another-number-editor")
        ProjectRoleAssignment.objects.create(
            project=self.project, domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.EDITOR, user=other,
        )
        self.client.force_authenticate(other)
        hidden = self.client.get(self.url, {"document_id": str(document.pk)})
        self.assertIsNone(hidden.data["allocation"])
        self.assertEqual(self.client.get(self.url, {"document_id": "invalid"}).status_code, 400)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.url, {"document_id": str(document.pk)}).status_code, 403)

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_edit_during_remote_allocation_does_not_overwrite_or_mark_used(self, client_class):
        document, payload = self.existing_payload()
        response = self.client.post(self.url, payload, format="json")
        def concurrent_edit(**kwargs):
            document.version += 1
            document.name = "Another editor's change"
            document.save()
            return GeneratedNumber(46, "CP-0046", "COVER_PAGE", "active", "")
        client_class.return_value.generate_number.side_effect = concurrent_edit
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)
        allocation = CoverPageNumberAllocation.objects.get(pk=response.data["id"])
        document.refresh_from_db()
        self.assertEqual(allocation.status, CoverPageNumberAllocation.Status.RECONCILIATION_REQUIRED)
        self.assertEqual(document.cover_page.number, "")
        self.assertEqual(document.name, "Another editor's change")
        client_class.return_value.mark_used.assert_not_called()

    def test_missing_cover_page_filter_is_scoped_paginated_and_excludes_archived(self):
        first, _ = self.existing_payload()
        second, _ = self.existing_payload()
        archived, _ = self.existing_payload()
        archived.is_archived = True
        archived.save()
        numbered, _ = self.existing_payload()
        numbered.cover_page.number = "CP-EXISTING"
        numbered.cover_page.save()
        other_project = Project.objects.exclude(pk=self.project.pk).first()
        other_cover = CoverPage.objects.create(project=other_project, number="", issue="A")
        ComplianceDocument.objects.create(project=other_project, cover_page=other_cover, name="Other project")
        url = self.url.replace("number-allocations/", "")
        self.client.force_authenticate(self.viewer)
        response = self.client.get(url, {"missing_cover_page": "true", "page_size": 1})
        next_page = self.client.get(url, {"missing_cover_page": "true", "page_size": 1, "page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(
            {response.data["results"][0]["id"], next_page.data["results"][0]["id"]},
            {str(first.pk), str(second.pk)},
        )
        present = self.client.get(url, {"missing_cover_page": "false"})
        self.assertEqual(present.data["count"], 1)
        self.assertEqual(present.data["results"][0]["id"], str(numbered.pk))
        self.assertEqual(self.client.get(url, {"missing_cover_page": "invalid"}).status_code, 400)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(url, {"missing_cover_page": "true"}).status_code, 403)

    @patch("compliance.numbering_formats.NumaratorClient")
    def test_format_fields_are_read_by_worker_with_owner_scoped_artifact(self, client_class):
        client_class.return_value.describe_format.return_value = {
            "code": "COVER_PAGE", "fields": [
                {"key": "department", "required": False, "default": "GEN", "max_length": 10},
                {"key": "branch", "required": True, "default": None, "max_length": 3},
            ],
        }
        url = self.url.replace("number-allocations", "numbering-options")
        payload = {"client_operation_id": str(uuid4()), "format_code": "COVER_PAGE"}
        with self.settings(NUMARATOR_API_KEY=""):
            response = self.client.post(url, payload, format="json")
            replay = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["id"], replay.data["id"])
        client_class.assert_not_called()
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        result = self.client.get(f"/api/jobs/{job.id}/download/")
        self.assertEqual(result.status_code, 200)
        import json
        data = json.loads(b"".join(result.streaming_content))
        self.assertEqual(data["fields"][0]["default"], "GEN")
        self.assertEqual(data["schema_version"], 1)
        client_class.return_value.close.assert_called_once()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(f"/api/jobs/{job.id}/download/").status_code, 404)
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 403)

    def test_format_read_rejects_other_project_format_and_requires_csrf(self):
        url = self.url.replace("number-allocations", "numbering-options")
        payload = {"client_operation_id": str(uuid4()), "format_code": "OTHER"}
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 400)
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.editor)
        payload["format_code"] = "COVER_PAGE"
        self.assertEqual(csrf_client.post(url, payload, format="json").status_code, 403)
        self.assertEqual(Job.objects.count(), 0)

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_custom_context_is_persisted_sent_and_part_of_idempotency(self, client_class):
        client = client_class.return_value
        client.describe_format.return_value = {"fields": [
            {"key": "department", "required": False, "default": "GEN", "max_length": 10},
        ]}
        client.generate_number.return_value = GeneratedNumber(81, "CP-ENG-81", "COVER_PAGE", "active", "")
        client.mark_used.return_value = GeneratedNumber(81, "CP-ENG-81", "COVER_PAGE", "used", "")
        payload = self.payload()
        payload["context_data"] = {"department": "ENG"}
        first = self.client.post(self.url, payload, format="json")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.data["context_data"], {"department": "ENG"})
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)
        self.assertEqual(client.generate_number.call_args.kwargs["context_data"], {"department": "ENG"})
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 200)
        payload["context_data"]["department"] = "GEN"
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 409)
        self.assertEqual(Job.objects.count(), 1)

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_missing_required_context_never_consumes_a_number(self, client_class):
        client = client_class.return_value
        client.describe_format.return_value = {"fields": [
            {"key": "branch", "required": True, "default": None, "max_length": 3},
        ]}
        response = self.client.post(self.url, self.payload(), format="json")
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)
        allocation = CoverPageNumberAllocation.objects.get(pk=response.data["id"])
        self.assertEqual(allocation.current_job.status, JobStatus.FAILED)
        self.assertEqual(allocation.current_job.error_code, "NUMARATOR_CONTEXT_INVALID")
        client.generate_number.assert_not_called()

    def test_context_rejects_nested_null_and_oversized_values(self):
        for context in ({"key": {}}, {"key": None}, {"key": "x" * 8193}, []):
            with self.subTest(context_type=type(context).__name__):
                payload = self.payload()
                payload["context_data"] = context
                self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertEqual(Job.objects.count(), 0)

    @patch("compliance.numbering_executor.NumaratorClient")
    def test_invalid_format_metadata_fails_without_external_write_reconciliation(self, client_class):
        from integrations.numarator.client import NumaratorConflictError
        client = client_class.return_value
        client.describe_format.side_effect = NumaratorConflictError("Invalid format contract")
        response = self.client.post(self.url, self.payload(), format="json")
        execute_claimed_job(claim_next_job("numbering-worker"), resolve_job_executor)
        allocation = CoverPageNumberAllocation.objects.get(pk=response.data["id"])
        self.assertEqual(allocation.current_job.status, JobStatus.FAILED)
        self.assertEqual(allocation.current_job.error_code, "NUMARATOR_FORMAT_UNAVAILABLE")
        self.assertEqual(allocation.status, CoverPageNumberAllocation.Status.REQUESTED)
        client.generate_number.assert_not_called()
