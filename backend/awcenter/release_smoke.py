"""Ingress-gating first-production smoke scenarios with exact cleanup."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APIClient

from compliance.models import ComplianceDocument, CoverPage, ImportAudit
from automations.models import EcrWorkflow
from dcc.models import DccRecord, JiraIssueDraft
from jobs.models import Job, JobStatus, WorkerHeartbeat
from jobs.services import create_job
from jobs.worker import claim_next_job, execute_claimed_job
from orgs.models import Project, ProjectRoleAssignment
from users.models import PasswordResetDelivery
from users.password_reset_notifications import (
    enqueue_password_reset,
    process_password_reset_deliveries,
)

from .job_executors import resolve_job_executor


class ReleaseSmokeError(RuntimeError):
    """Identify a failed ingress gate without leaking response bodies or secrets."""


def assert_fresh_install() -> None:
    """Refuse destructive smoke cleanup when business state already exists."""

    occupied = {
        "compliance_documents": ComplianceDocument.objects.exists(),
        "compliance_import_audits": ImportAudit.objects.exists(),
        "dcc_records": DccRecord.objects.exists(),
        "jira_issue_drafts": JiraIssueDraft.objects.exists(),
        "ecr_workflows": EcrWorkflow.objects.exists(),
        "jobs": Job.objects.exists(),
        "password_reset_deliveries": PasswordResetDelivery.objects.exists(),
    }
    names = [name for name, present in occupied.items() if present]
    if names:
        raise ReleaseSmokeError(
            "First-production smoke requires an unused database; found: "
            + ", ".join(names)
        )


def require_operator(username: str):
    """Resolve an existing active superuser named by the operator."""

    user = get_user_model().objects.filter(username=username, is_active=True).first()
    if user is None or not user.is_superuser:
        raise ReleaseSmokeError("The named release operator is not an active superuser.")
    return user


def run_core_smoke(*, operator_username: str, project_slug: str) -> dict:
    """Exercise browser auth, roles, import/lifecycle, DCC, and private download."""

    assert_fresh_install()
    require_operator(operator_username)
    project = Project.objects.filter(slug=project_slug, enabled=True).first()
    if project is None:
        raise ReleaseSmokeError("The smoke project is not enabled or was not seeded.")

    run_id = uuid.uuid4().hex
    username = f"release-smoke-{run_id[:16]}"
    password = secrets.token_urlsafe(32)
    user = None
    outsider = None
    document_id = None
    cover_page_id = None
    audit_id = None
    job_id = None
    worker_id = f"release-smoke-{run_id}"
    try:
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@invalid.example",
            password=password,
        )
        outsider = get_user_model().objects.create_user(
            username=f"release-smoke-outsider-{run_id[:16]}",
            password=secrets.token_urlsafe(32),
        )
        smoke_host = _smoke_host()
        referer = f"https://{smoke_host}/app/"
        client = APIClient(enforce_csrf_checks=True, HTTP_HOST=smoke_host)
        bootstrap = client.get("/api/session/", secure=True)
        _expect(bootstrap.status_code == 200, "Session bootstrap failed.")
        _expect(bootstrap.data == {"state": "anonymous", "user": None}, "Session was not anonymous.")
        csrf_token = bootstrap.cookies.get("csrftoken")
        _expect(csrf_token is not None, "Session bootstrap did not issue a CSRF cookie.")
        client.credentials(HTTP_REFERER=referer)
        rejected_login = client.post(
            "/api/session/",
            {"username": username, "password": password},
            format="json",
            secure=True,
        )
        _expect(rejected_login.status_code == 403, "Login accepted a request without CSRF.")
        login = client.post(
            "/api/session/",
            {"username": username, "password": password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token.value,
            secure=True,
        )
        _expect(login.status_code == 200, "Session login failed.")
        _expect(login.data.get("state") == "authenticated", "Login did not establish a session.")
        _expect("token" not in login.data, "Login exposed a browser token.")
        authenticated_csrf = client.cookies.get("csrftoken")
        _expect(authenticated_csrf is not None, "Login did not rotate the CSRF cookie.")
        client.credentials(
            HTTP_REFERER=referer,
            HTTP_X_CSRFTOKEN=authenticated_csrf.value,
        )

        before_roles = client.get("/api/projects/", secure=True)
        _expect(before_roles.status_code == 200 and before_roles.data == [], "Roleless project catalog was not empty.")
        _grant_smoke_roles(user, project)
        catalog = client.get("/api/projects/", secure=True)
        _expect(catalog.status_code == 200, "Project catalog failed after role assignment.")
        project_payload = next(
            (item for item in catalog.data if item.get("slug") == project.slug),
            None,
        )
        _expect(project_payload is not None, "The authorized smoke project was not visible.")
        _expect(
            project_payload.get("roles", {}).get("compliance") == "editor"
            and project_payload.get("roles", {}).get("dcc") == "operator",
            "Project roles were not projected correctly.",
        )

        workbook = _compliance_workbook(run_id)
        preview = client.post(
            f"/api/projects/{project.slug}/compliance-documents/imports/preview/",
            {"file": _workbook_upload(workbook)},
            format="multipart",
            secure=True,
        )
        _expect(preview.status_code == 200, "Compliance import preview failed.")
        _expect(preview.data.get("created_count") == 1, "Compliance preview was not a create.")
        confirmation = client.post(
            f"/api/projects/{project.slug}/compliance-documents/imports/confirm/",
            {
                "file": _workbook_upload(workbook),
                "confirmation_token": preview.data.get("confirmation_token"),
            },
            format="multipart",
            secure=True,
        )
        _expect(confirmation.status_code == 201, "Compliance import confirmation failed.")
        audit_id = confirmation.data.get("audit_id")
        document = ComplianceDocument.objects.get(
            project=project,
            tech_doc_no=f"SMOKE-TD-{run_id[:12]}",
        )
        document_id = document.pk
        cover_page_id = document.cover_page_id
        transition = client.post(
            f"/api/projects/{project.slug}/compliance-documents/{document.pk}/transitions/",
            {
                "version": document.version,
                "status": "to_be_issued",
                "effective_date": date.today().isoformat(),
                "reason": "First-production release smoke",
            },
            format="json",
            secure=True,
        )
        _expect(transition.status_code == 200, "Compliance lifecycle transition failed.")

        snapshot = _dcc_snapshot(project, run_id)
        job, created = create_job(
            user,
            "dcc.create_document",
            "Release smoke DCC document",
            {"issue_key": snapshot["issue_key"]},
            ContentFile(
                json.dumps(snapshot, separators=(",", ":"), sort_keys=True).encode("utf-8"),
                name="release-smoke-dcc.json",
            ),
            f"release-smoke-{run_id}",
            f"release-smoke-{run_id}",
        )
        _expect(created, "DCC smoke job was not created.")
        job_id = job.pk
        claimed = claim_next_job(worker_id, eligible_kinds=("dcc.create_document",))
        _expect(claimed is not None and claimed.pk == job.pk, "DCC smoke job was not claimed.")
        execute_claimed_job(claimed, resolve_job_executor)
        job.refresh_from_db()
        _expect(job.status == JobStatus.SUCCEEDED, "DCC smoke job did not succeed.")
        _expect(bool(job.output_file) and len(job.output_sha256) == 64, "DCC artifact was not fenced.")

        owner_download = client.get(f"/api/jobs/{job.pk}/download/", secure=True)
        _expect(owner_download.status_code == 200, "DCC artifact owner download failed.")
        output = b"".join(owner_download.streaming_content)
        _expect(output.startswith(b"PK"), "DCC artifact is not a DOCX archive.")
        outsider_client = APIClient(HTTP_HOST=smoke_host)
        outsider_client.force_authenticate(outsider)
        denied_download = outsider_client.get(f"/api/jobs/{job.pk}/download/")
        _expect(denied_download.status_code == 404, "Private artifact leaked to another user.")

        logout = client.delete(
            "/api/session/",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            secure=True,
        )
        _expect(logout.status_code == 204, "Session logout failed.")
        _expect(client.get("/api/session/", secure=True).data.get("state") == "anonymous", "Logout did not invalidate the session.")
        return {
            "project": project.slug,
            "session": "passed",
            "compliance": "passed",
            "dcc_job": "passed",
            "private_download": "passed",
        }
    finally:
        if job_id:
            Job.objects.filter(pk=job_id).delete()
        WorkerHeartbeat.objects.filter(worker_id=worker_id).delete()
        if document_id:
            ComplianceDocument.objects.filter(pk=document_id).delete()
            ComplianceDocument.history.model.objects.filter(id=document_id).delete()
        if cover_page_id:
            CoverPage.objects.filter(pk=cover_page_id).delete()
            CoverPage.history.model.objects.filter(id=cover_page_id).delete()
        if audit_id:
            ImportAudit.objects.filter(pk=audit_id).delete()
        if user:
            ProjectRoleAssignment.objects.filter(user=user).delete()
            user.delete()
        if outsider:
            outsider.delete()


def run_notification_smoke(*, operator_username: str, recipient: str) -> dict:
    """Send one fenced password-reset canary from the notification boundary."""

    assert_fresh_install()
    require_operator(operator_username)
    run_id = uuid.uuid4().hex
    user = None
    try:
        user = get_user_model().objects.create_user(
            username=f"release-mail-smoke-{run_id[:16]}",
            email=recipient,
            password=secrets.token_urlsafe(32),
        )
        delivery, created = enqueue_password_reset(user)
        _expect(created and delivery is not None, "Notification smoke was not queued.")
        result = process_password_reset_deliveries()
        delivery.refresh_from_db()
        _expect(
            result == {"processed": 1, "sent": 1, "failed": 0}
            and delivery.status == PasswordResetDelivery.Status.SENT,
            "Notification smoke was not delivered.",
        )
        _expect(delivery.message_id.startswith("<password-reset-"), "Notification Message-ID was not deterministic.")
        return {"notification": "passed", "message_id": delivery.message_id}
    finally:
        if user:
            user.delete()


def _grant_smoke_roles(user, project) -> None:
    for domain, role in (
        (ProjectRoleAssignment.Domain.COMPLIANCE, ProjectRoleAssignment.Role.EDITOR),
        (ProjectRoleAssignment.Domain.ORGANIZATION, ProjectRoleAssignment.Role.VIEWER),
        (ProjectRoleAssignment.Domain.DCC, ProjectRoleAssignment.Role.OPERATOR),
    ):
        ProjectRoleAssignment.objects.create(
            user=user,
            project=project,
            domain=domain,
            role=role,
        )


def _compliance_workbook(run_id: str) -> bytes:
    output = BytesIO()
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Document Name", "Cover Page Number", "Technical Document No"])
    worksheet.append(
        [
            f"Release smoke {run_id[:12]}",
            f"SMOKE-CP-{run_id[:12]}",
            f"SMOKE-TD-{run_id[:12]}",
        ]
    )
    workbook.save(output)
    return output.getvalue()


def _workbook_upload(content: bytes):
    return SimpleUploadedFile(
        "release-smoke-compliance.xlsx",
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _dcc_snapshot(project, run_id: str) -> dict:
    issue_key = f"SMOKE-{run_id[:8].upper()}"
    return {
        "schema_version": 1,
        "issue_key": issue_key,
        "project_slug": project.slug,
        "project_slugs": [project.slug],
        "project_ids": [project.pk],
        "project_label": project.name,
        "output_name": f"{issue_key}.docx",
        "panel_count": 0,
        "placeholders": {"Design_Change_Title": "First-production release smoke"},
    }


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseSmokeError(message)


def _smoke_host() -> str:
    """Choose one configured concrete host for same-origin CSRF checks."""

    for value in settings.ALLOWED_HOSTS:
        host = str(value).strip().lstrip(".")
        if host and host != "*":
            return host
    raise ReleaseSmokeError("No concrete ALLOWED_HOSTS value is available for release smoke.")
