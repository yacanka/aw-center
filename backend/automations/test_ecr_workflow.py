"""Acceptance and security tests for the server-owned ECR workflow."""

import json
import uuid
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from integrations.jira.sessions import (
    JiraSessionNotConnected,
    clear_jira_session,
    store_jira_session,
)
from jobs.contracts import JobExecutionFailure, JobExecutionUncertain
from jobs.execution import bind_execution
from jobs.models import Job, JobStatus
from jobs.services import set_job_state
from jobs.tests.base import JobTestCase
from orgs.models import Project, ProjectRoleAssignment

from .ecr_publication_executor import execute_ecr_jira_publication
from .ecr_parser import SNAPSHOT_KEYS
from .ecr_publication_state import fail_ecr_publication
from .models import EcrWorkflow, EcrWorkflowStatus

TEST_FERNET_KEY = Fernet.generate_key().decode("ascii")


@override_settings(
    DEBUG=True,
    JIRA_ENABLED=True,
    JIRA_URL="https://jira.example.test",
    JIRA_SESSION_ENCRYPTION_KEY=TEST_FERNET_KEY,
    JIRA_SESSION_TTL_SECONDS=60,
)
class EcrWorkflowApiTests(JobTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.project = Project.objects.get(slug="hys")
        self.assignment = grant_publisher(self.user, self.project)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_create_parses_sanitized_snapshot_and_exact_replay(self):
        first = self.create_workflow(key="ecr-create-request-1")
        replay = self.create_workflow(key="ecr-create-request-1")
        changed = self.create_workflow(
            key="ecr-create-request-1",
            title="Different change",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(first.data["snapshot"]["ecr_number"], "ECD-42 / REV")
        self.assertEqual(first.data["snapshot"]["title"], "Validated change")
        self.assertEqual(set(first.data["snapshot"]), set(SNAPSHOT_KEYS))
        self.assertEqual(first.data["status"], EcrWorkflowStatus.REVIEW)
        self.assertNotIn("owner", first.data)
        serialized = json.dumps(first.data).casefold()
        self.assertNotIn("private_media", serialized)
        self.assertNotIn("marker_label", serialized)
        self.assertNotIn("source_sha256", serialized)

        listed = self.client.get("/api/workflows/ecr/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(set(listed.data), {"count", "next", "previous", "results"})
        self.assertEqual(listed.data["count"], 1)

    def test_get_collection_and_detail_do_not_mutate_workflow_state(self):
        created = self.create_workflow(key="ecr-read-only-get-1").data
        workflow = EcrWorkflow.objects.get(pk=created["id"])
        original = (
            workflow.status,
            workflow.version,
            workflow.updated_at,
            workflow.events.count(),
        )

        collection = self.client.get("/api/workflows/ecr/")
        detail = self.client.get(f"/api/workflows/ecr/{workflow.id}/")

        self.assertEqual(collection.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        workflow.refresh_from_db()
        self.assertEqual(
            (
                workflow.status,
                workflow.version,
                workflow.updated_at,
                workflow.events.count(),
            ),
            original,
        )

    def test_invalid_pdf_and_inline_credentials_are_rejected_safely(self):
        invalid = self.client.post(
            "/api/workflows/ecr/",
            {
                "file": SimpleUploadedFile(
                    "invalid.pdf",
                    b"%PDF-1.4\nnot-a-valid-document",
                    content_type="application/pdf",
                ),
                "project_slugs": json.dumps([self.project.slug]),
            },
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="ecr-invalid-pdf-1",
        )
        credential = self.client.post(
            "/api/workflows/ecr/",
            {
                "file": ecr_upload(),
                "project_slugs": json.dumps([self.project.slug]),
                "JSESSIONID": "must-never-be-persisted",
            },
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="ecr-inline-credential-1",
        )
        query_credential = self.client.get(
            "/api/workflows/ecr/?JSESSIONID=must-never-enter-a-url"
        )

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.data["code"], "ECR_PDF_INVALID")
        self.assertNotIn("pdfplumber", json.dumps(invalid.data).casefold())
        self.assertEqual(credential.status_code, 400)
        self.assertEqual(credential.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        self.assertEqual(query_credential.status_code, 400)
        self.assertEqual(
            query_credential.data["code"],
            "JIRA_SESSION_CANONICAL_REQUIRED",
        )
        self.assertNotIn("must-never-enter-a-url", json.dumps(query_credential.data))
        self.assertFalse(EcrWorkflow.objects.filter(create_idempotency_key="ecr-inline-credential-1"))

    def test_review_requires_owner_role_and_optimistic_version(self):
        created = self.create_workflow(key="ecr-review-request-1").data
        url = f"/api/workflows/ecr/{created['id']}/approve/"

        self.client.force_authenticate(self.other_user)
        hidden = self.client.post(url, approval_payload(created["version"]), format="json")
        self.client.force_authenticate(self.user)
        stale = self.client.post(url, approval_payload(created["version"] + 1), format="json")
        approved = self.client.post(url, approval_payload(created["version"]), format="json")

        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "ECR_VERSION_CONFLICT")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], EcrWorkflowStatus.APPROVED)
        self.assertEqual(approved.data["approval"]["subtasks"][0]["due_date"], "2026-09-01")
        self.assertFalse(approved.data["allowed_actions"]["approve"])
        self.assertTrue(approved.data["allowed_actions"]["publish"])

    @patch("automations.ecr_views.jira_connector_for")
    def test_preflight_exposes_required_jira_fields_before_approval(self, connector_for):
        created = self.create_workflow(key="ecr-preflight-request-1").data
        task_metadata = [
            {
                "id": identifier,
                "name": identifier.title(),
                "required": True,
                "hasDefaultValue": False,
                "schema": {"type": "string"},
                "allowedValues": [],
            }
            for identifier in ("summary", "description", "labels", "customfield_123")
        ]
        subtask_metadata = [
            {
                "id": identifier,
                "name": identifier.title(),
                "required": True,
                "hasDefaultValue": False,
                "schema": {"type": "string"},
                "allowedValues": [],
            }
            for identifier in ("summary", "parent")
        ]
        connector_for.return_value.get_create_fields.side_effect = [
            task_metadata,
            subtask_metadata,
            task_metadata,
            subtask_metadata,
        ]
        payload = approval_payload(created["version"])

        missing = self.client.post(
            f"/api/workflows/ecr/{created['id']}/preflight/",
            payload,
            format="json",
        )
        payload["extra_fields"] = {"customfield_123": "Certification"}
        ready = self.client.post(
            f"/api/workflows/ecr/{created['id']}/preflight/",
            payload,
            format="json",
        )

        self.assertEqual(missing.status_code, 200)
        self.assertFalse(missing.data["ready"])
        self.assertEqual(missing.data["missing_fields"][0]["id"], "customfield_123")
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.data["ready"])

    def test_multi_project_publish_requires_publisher_on_every_project(self):
        second_project = Project.objects.get(slug="piku")
        second_assignment = ProjectRoleAssignment.objects.create(
            user=self.user,
            project=second_project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=ProjectRoleAssignment.Role.OPERATOR,
        )
        created = self.client.post(
            "/api/workflows/ecr/",
            {
                "file": ecr_upload(),
                "project_slugs": json.dumps(
                    [self.project.slug, second_project.slug]
                ),
            },
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="ecr-multi-project-create-1",
        ).data
        approved = self.client.post(
            f"/api/workflows/ecr/{created['id']}/approve/",
            approval_payload(created["version"]),
            format="json",
        ).data
        connect_session(self.user)

        blocked = self.client.post(
            f"/api/workflows/ecr/{created['id']}/publish/",
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-multi-project-publish-1",
        )

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["code"], "DCC_PROJECT_ROLE_REQUIRED")
        self.assertFalse(Job.objects.exists())
        second_assignment.role = ProjectRoleAssignment.Role.PUBLISHER
        second_assignment.save()
        published = self.client.post(
            f"/api/workflows/ecr/{created['id']}/publish/",
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-multi-project-publish-1",
        )
        self.assertEqual(published.status_code, 201)

    def test_publish_is_credential_free_idempotent_and_cancel_projects_to_workflow(self):
        approved = self.approved_workflow("ecr-publish-create-1")
        publish_url = f"/api/workflows/ecr/{approved['id']}/publish/"
        missing_session = self.client.post(
            publish_url,
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-publish-request-1",
        )
        connect_session(self.user)
        first = self.client.post(
            publish_url,
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-publish-request-1",
        )
        replay = self.client.post(
            publish_url,
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-publish-request-1",
        )

        self.assertEqual(missing_session.status_code, 409)
        self.assertEqual(missing_session.data["code"], "JIRA_SESSION_REQUIRED")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(first.data["publication"]["job_id"], replay.data["publication"]["job_id"])
        job = Job.objects.get(pk=first.data["publication"]["job_id"])
        clear_jira_session(self.user)
        with patch(
            "automations.ecr_publication_jobs.find_idempotent_job",
            side_effect=[None, job],
        ):
            raced_replay = self.client.post(
                publish_url,
                {"version": approved["version"]},
                format="json",
                HTTP_IDEMPOTENCY_KEY="ecr-publish-request-1",
            )
        self.assertEqual(raced_replay.status_code, 200)
        self.assertEqual(raced_replay.headers["Idempotency-Replayed"], "true")
        self.assertTrue(job.reconcile_on_lease_loss)
        serialized = json.dumps(job.parameters).casefold()
        with job.input_file.open("rb") as source:
            stored = source.read().decode("utf-8").casefold()
        for secret_name in ("jsessionid", "password", "credential", "token"):
            self.assertNotIn(secret_name, serialized)
            self.assertNotIn(secret_name, stored)
        cancelled = self.client.post(f"/api/jobs/{job.id}/cancel/", {}, format="json")
        workflow = EcrWorkflow.objects.get(pk=approved["id"])
        self.assertEqual(workflow.status, EcrWorkflowStatus.CANCELLED)
        detail = self.client.get(f"/api/workflows/ecr/{approved['id']}/")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(detail.data["status"], EcrWorkflowStatus.CANCELLED)
        self.assertTrue(detail.data["allowed_actions"]["resume"])

    def create_workflow(self, *, key, title="Validated change"):
        return self.client.post(
            "/api/workflows/ecr/",
            {
                "file": ecr_upload(title=title),
                "project_slugs": json.dumps([self.project.slug]),
            },
            format="multipart",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def approved_workflow(self, key):
        created = self.create_workflow(key=key).data
        response = self.client.post(
            f"/api/workflows/ecr/{created['id']}/approve/",
            approval_payload(created["version"]),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response.data


@override_settings(
    DEBUG=True,
    JIRA_ENABLED=True,
    JIRA_URL="https://jira.example.test",
    JIRA_SESSION_ENCRYPTION_KEY=TEST_FERNET_KEY,
    JIRA_SESSION_TTL_SECONDS=60,
)
class EcrPublicationExecutorTests(JobTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.project = Project.objects.get(slug="hys")
        self.assignment = grant_publisher(self.user, self.project)
        self.client.force_authenticate(self.user)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_create_review_approve_publish_and_resume_after_session_expiry(self):
        workflow, job = self.queued_workflow("ecr-session-expiry-1")
        clear_jira_session(self.user)

        with active_job(job), patch(
            "automations.ecr_publication_executor.jira_connector_for",
            side_effect=JiraSessionNotConnected(),
        ):
            with self.assertRaises(JobExecutionFailure) as raised:
                execute_ecr_jira_publication(job)

        self.assertEqual(raised.exception.code, "JIRA_RECONNECT_REQUIRED")
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, EcrWorkflowStatus.FAILED)
        terminalize(job, JobStatus.FAILED, "JIRA_RECONNECT_REQUIRED")
        connect_session(self.user)
        resumed = self.client.post(
            f"/api/workflows/ecr/{workflow.id}/resume/",
            {"version": workflow.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-session-resume-1",
        )
        self.assertEqual(resumed.status_code, 201)
        resume_job = Job.objects.get(pk=resumed.data["publication"]["job_id"])
        connector = ready_connector(subtask_count=1)

        with active_job(resume_job), patch(
            "automations.ecr_publication_executor.jira_connector_for",
            return_value=connector,
        ):
            result = execute_ecr_jira_publication(resume_job)

        result.path.unlink(missing_ok=True)
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, EcrWorkflowStatus.PUBLISHED)
        self.assertEqual(workflow.jira_issue_key, "CHN-101")
        self.assertTrue(workflow.publication_state["attachment_confirmed"])
        self.assertEqual(len(workflow.publication_state["subtask_keys"]), 1)

    def test_ambiguous_parent_write_uses_read_only_reconciliation_before_resume(self):
        workflow, job = self.queued_workflow("ecr-ambiguous-create-1")
        ambiguous = ready_connector(subtask_count=1)
        ambiguous.create_issue.side_effect = RuntimeError("private upstream endpoint")

        with active_job(job), patch(
            "automations.ecr_publication_executor.jira_connector_for",
            return_value=ambiguous,
        ):
            with self.assertRaises(JobExecutionUncertain) as raised:
                execute_ecr_jira_publication(job)

        self.assertNotIn("private upstream", str(raised.exception))
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, EcrWorkflowStatus.RECONCILIATION_REQUIRED)
        self.assertEqual(workflow.publication_state["uncertain_operation"], "parent")
        terminalize(job, JobStatus.RECONCILIATION_REQUIRED, "RECONCILIATION_REQUIRED")

        reconcile_response = self.client.post(
            f"/api/workflows/ecr/{workflow.id}/resume/",
            {"version": workflow.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-reconcile-request-1",
        )
        reconcile_job = Job.objects.get(pk=reconcile_response.data["publication"]["job_id"])
        reconciliation = ready_connector(subtask_count=1)
        reconciliation.find_issue_by_label.side_effect = lambda label: (
            SimpleNamespace(key="CHN-501") if label == workflow.marker_label else None
        )
        reconciliation.find_attachment_by_filename.return_value = None

        with active_job(reconcile_job), patch(
            "automations.ecr_publication_executor.jira_connector_for",
            return_value=reconciliation,
        ):
            with self.assertRaises(JobExecutionFailure) as missing:
                execute_ecr_jira_publication(reconcile_job)

        self.assertEqual(missing.exception.code, "ECR_RECONCILIATION_NOT_FOUND")
        reconciliation.create_issue.assert_not_called()
        reconciliation.add_attachment.assert_not_called()
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, EcrWorkflowStatus.FAILED)
        terminalize(reconcile_job, JobStatus.FAILED, missing.exception.code)

        resume_response = self.client.post(
            f"/api/workflows/ecr/{workflow.id}/resume/",
            {"version": workflow.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ecr-after-reconcile-1",
        )
        resume_job = Job.objects.get(pk=resume_response.data["publication"]["job_id"])
        resumed = ready_connector(subtask_count=1)
        resumed.find_issue_by_label.side_effect = lambda label: (
            SimpleNamespace(key="CHN-501") if label == workflow.marker_label else None
        )
        resumed.create_issue.return_value = SimpleNamespace(key="CHN-502")

        with active_job(resume_job), patch(
            "automations.ecr_publication_executor.jira_connector_for",
            return_value=resumed,
        ):
            result = execute_ecr_jira_publication(resume_job)

        result.path.unlink(missing_ok=True)
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, EcrWorkflowStatus.PUBLISHED)
        self.assertEqual(workflow.jira_issue_key, "CHN-501")
        self.assertEqual(ambiguous.create_issue.call_count, 1)
        self.assertEqual(resumed.create_issue.call_count, 1)

    def test_dispatch_cancellation_does_not_override_confirmed_success(self):
        workflow, job = self.queued_workflow("ecr-cancel-success-1")
        connector = ready_connector(subtask_count=1)

        with active_job(job, status=JobStatus.CANCEL_REQUESTED), patch(
            "automations.ecr_publication_executor.jira_connector_for",
            return_value=connector,
        ):
            result = execute_ecr_jira_publication(job)

        result.path.unlink(missing_ok=True)
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, EcrWorkflowStatus.PUBLISHED)
        self.assertEqual(workflow.jira_issue_key, "CHN-101")

    def test_cancel_race_projects_intermediate_failure_to_reconciliation(self):
        workflow, job = self.queued_workflow("ecr-cancel-failure-1")

        with active_job(job, status=JobStatus.CANCEL_REQUESTED):
            fail_ecr_publication(
                job,
                "ECR_JIRA_WRITE_REJECTED",
                "JIRA rejected the ECR publication operation.",
            )
            workflow.refresh_from_db()
            self.assertEqual(workflow.status, EcrWorkflowStatus.FAILED)
            set_job_state(
                job,
                JobStatus.RECONCILIATION_REQUIRED,
                job.progress,
                "Confirm the external system state before submitting another write.",
                "RECONCILIATION_REQUIRED",
            )

        workflow.refresh_from_db()
        self.assertEqual(
            workflow.status,
            EcrWorkflowStatus.RECONCILIATION_REQUIRED,
        )
        self.assertEqual(
            workflow.last_error_code,
            "ECR_RECONCILIATION_REQUIRED",
        )

    def test_worker_rechecks_publisher_role_before_provider_access(self):
        workflow, job = self.queued_workflow("ecr-role-loss-1")
        self.assignment.role = ProjectRoleAssignment.Role.VIEWER
        self.assignment.save()

        with active_job(job), patch(
            "automations.ecr_publication_executor.jira_connector_for"
        ) as connector_for:
            with self.assertRaises(JobExecutionFailure) as raised:
                execute_ecr_jira_publication(job)

        self.assertEqual(raised.exception.code, "DCC_PROJECT_ROLE_REQUIRED")
        connector_for.assert_not_called()
        workflow.refresh_from_db()
        self.assertEqual(workflow.status, EcrWorkflowStatus.FAILED)

    def queued_workflow(self, key):
        created = self.client.post(
            "/api/workflows/ecr/",
            {
                "file": ecr_upload(),
                "project_slugs": json.dumps([self.project.slug]),
            },
            format="multipart",
            HTTP_IDEMPOTENCY_KEY=f"{key}-create",
        ).data
        approved = self.client.post(
            f"/api/workflows/ecr/{created['id']}/approve/",
            approval_payload(created["version"]),
            format="json",
        ).data
        connect_session(self.user)
        queued = self.client.post(
            f"/api/workflows/ecr/{created['id']}/publish/",
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"{key}-publish",
        )
        self.assertEqual(queued.status_code, 201)
        workflow = EcrWorkflow.objects.get(pk=created["id"])
        job = Job.objects.get(pk=queued.data["publication"]["job_id"])
        return workflow, job


def grant_publisher(user, project):
    return ProjectRoleAssignment.objects.create(
        user=user,
        project=project,
        domain=ProjectRoleAssignment.Domain.DCC,
        role=ProjectRoleAssignment.Role.PUBLISHER,
    )


def connect_session(user):
    return store_jira_session(
        user,
        "opaque-ecr-session-value",
        {"username": "ecr-user", "display_name": "ECR User"},
    )


def approval_payload(version):
    return {
        "version": version,
        "project_key": "CHN",
        "subtasks": [
            {
                "summary": "Structural assessment",
                "description": "Review the proposed ECR change.",
                "assignee": "reviewer",
                "priority": "Medium",
                "due_date": "2026-09-01",
            }
        ],
    }


@contextmanager
def active_job(job, *, status=JobStatus.RUNNING):
    job.status = status
    job.worker_id = "ecr-test-worker"
    job.execution_token = uuid.uuid4()
    job.lease_expires_at = timezone.now() + timedelta(minutes=5)
    job.save()
    job.refresh_from_db()
    with bind_execution(job):
        yield job


def terminalize(job, status, code):
    Job.objects.filter(pk=job.pk).update(
        status=status,
        error_code=code,
        worker_id="",
        execution_token=None,
        lease_expires_at=None,
        completed_at=timezone.now(),
    )
    job.refresh_from_db()


def ready_connector(subtask_count):
    connector = Mock()
    connector.find_issue_by_label.return_value = None
    connector.find_attachment_by_filename.return_value = None
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
    connector.build_subtask_fields.side_effect = lambda **values: {
        "project": "CHN",
        "summary": values["summary"],
        "description": values["description"],
        "issuetype": {"name": "Sub-task"},
        "parent": {"key": "CHN-101"},
        **values["extra_fields"],
    }
    connector.create_issue.side_effect = [
        SimpleNamespace(key=f"CHN-{index}")
        for index in range(101, 102 + subtask_count)
    ]
    connector.add_attachment.return_value = SimpleNamespace(id="attachment")
    return connector


def ecr_upload(*, title="Validated change"):
    return SimpleUploadedFile(
        "change.pdf",
        ecr_pdf(title),
        content_type="application/pdf",
    )


def ecr_pdf(title):
    cells = {
        (2, 0): title,
        (4, 0): "ECD-42 / REV-A-extra",
        (4, 1): "AW Center",
        (4, 2): "Minor",
        (4, 3): "Design",
        (7, 0): "Initial",
        (9, 1): "Aircraft 1",
        (10, 1): "Certification",
        (11, 1): "Requestor",
        (13, 1): "Originator",
        (14, 1): "27/10",
        (15, 1): "Justification",
        (16, 1): "Solution",
        (17, 1): "Consequence",
        (18, 1): "Systems",
    }
    return pdf_document(table_commands(cells))


def table_commands(cells):
    columns, top, row_height = [30, 180, 310, 440, 570], 740, 35
    commands = ["0.5 w"]
    commands.extend(f"{x} 75 m {x} {top} l S" for x in columns)
    commands.extend(
        f"30 {top - row * row_height} m 570 {top - row * row_height} l S"
        for row in range(20)
    )
    for (row, column), value in cells.items():
        x, y = columns[column] + 3, top - (row + 1) * row_height + 12
        commands.append(f"BT /F1 8 Tf {x} {y} Td ({escape_pdf(value)}) Tj ET")
    return "\n".join(commands).encode()


def pdf_document(stream):
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    body, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body.extend(b"%d 0 obj\n%s\nendobj\n" % (index, obj))
    xref = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    body.extend("".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]).encode())
    body.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(body)


def escape_pdf(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
