"""Admin-only permanent deletion tests for compliance documents."""

import uuid
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from orgs.models import Project

from .models import (
    ComplianceDocument,
    CoverPage,
    CoverPageNumberAllocation,
    DocumentPurgeAudit,
)


class ComplianceDocumentAdminTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Admin purge", slug="admin-purge")
        self.cover_page = CoverPage.objects.create(
            project=self.project,
            number="CP-ADMIN",
            issue="A",
        )
        self.superuser = get_user_model().objects.create_superuser(
            username="purge-admin",
            password="safe-pass",
        )

    def create_document(self, *, archived):
        return ComplianceDocument.objects.create(
            project=self.project,
            cover_page=self.cover_page,
            name=f"Admin document {uuid.uuid4()}",
            is_archived=archived,
            archived_by=self.superuser if archived else None,
            archive_reason="Ready for purge" if archived else "",
        )

    @staticmethod
    def delete_url(document):
        return reverse(
            "admin:compliance_compliancedocument_delete",
            args=[document.pk],
        )

    def test_superuser_can_delete_archived_document_and_audit_is_retained(self):
        document = self.create_document(archived=True)
        allocation = CoverPageNumberAllocation.objects.create(
            project=self.project,
            actor=self.superuser,
            client_operation_id=uuid.uuid4(),
            request_hash="a" * 64,
            document_snapshot={"name": document.name},
            format_code="CP",
            credential_fingerprint="fingerprint",
            status=CoverPageNumberAllocation.Status.COMPLETED,
            cover_page=self.cover_page,
            document=document,
        )
        self.client.force_login(self.superuser)

        confirmation = self.client.get(self.delete_url(document))
        response = self.client.post(self.delete_url(document), {"post": "yes"})

        self.assertEqual(confirmation.status_code, 200)
        self.assertRedirects(response, reverse("admin:index"))
        self.assertFalse(ComplianceDocument.objects.filter(pk=document.pk).exists())
        allocation.refresh_from_db()
        self.assertIsNone(allocation.document_id)

        audit = DocumentPurgeAudit.objects.get(document_id=document.pk)
        self.assertEqual(audit.project, self.project)
        self.assertEqual(audit.document_version, document.version)
        self.assertEqual(audit.purged_by, self.superuser)
        self.assertEqual(audit.reason, "Deleted through Django admin.")
        self.assertTrue(
            ComplianceDocument.history.filter(
                id=document.pk,
                history_type="-",
                history_user=self.superuser,
            ).exists()
        )

    def test_active_document_cannot_be_deleted_from_admin(self):
        document = self.create_document(archived=False)
        self.client.force_login(self.superuser)

        response = self.client.post(self.delete_url(document), {"post": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(ComplianceDocument.objects.filter(pk=document.pk).exists())
        self.assertFalse(DocumentPurgeAudit.objects.filter(document_id=document.pk).exists())

    def test_non_superuser_cannot_delete_even_with_model_permission(self):
        document = self.create_document(archived=True)
        staff_user = get_user_model().objects.create_user(
            username="compliance-staff",
            password="safe-pass",
            is_staff=True,
        )
        staff_user.user_permissions.add(
            Permission.objects.get(codename="delete_compliancedocument")
        )
        self.client.force_login(staff_user)

        response = self.client.post(self.delete_url(document), {"post": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(ComplianceDocument.objects.filter(pk=document.pk).exists())

    def test_management_command_uses_the_shared_purge_path(self):
        document = self.create_document(archived=True)
        stdout = StringIO()

        call_command(
            "purge_compliance_document",
            document_id=document.pk,
            confirm_document_id=document.pk,
            expected_version=document.version,
            operator=self.superuser.username,
            reason="Approved command purge",
            stdout=stdout,
        )

        self.assertFalse(ComplianceDocument.objects.filter(pk=document.pk).exists())
        self.assertTrue(DocumentPurgeAudit.objects.filter(document_id=document.pk).exists())
        self.assertIn(str(document.pk), stdout.getvalue())
