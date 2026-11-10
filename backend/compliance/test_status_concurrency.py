"""Real database races for status assignments and catalog deletion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import APIException

from orgs.models import Project
from .models import ComplianceDocument, CoverPage, DocumentStatus
from .services import transition_document
from .status_catalog import create_status, delete_status


@override_settings(DEBUG=False)
class StatusConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.project, _ = Project.objects.get_or_create(slug="ozgur", defaults={"name": "Ozgur"})
        self.user = get_user_model().objects.create_user("concurrent-status-user")

    def race(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            try:
                barrier.wait(timeout=10)
                operation()
                return 200
            except APIException as error:
                return error.status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(run, operations, timeout=30))

    def test_assignment_and_delete_never_leave_dangling_current_status(self):
        option = create_status(self.project, "Concurrent Review")
        document = ComplianceDocument.objects.create(
            project=self.project, name="Document",
            cover_page=CoverPage.objects.create(project=self.project, number="CP"),
        )
        outcomes = self.race([
            lambda: transition_document(project=self.project, document_id=document.pk,
                expected_version=1, new_status=option.value, effective_date=date.today(),
                next_action_due_date=None, reason="Concurrency test", user=self.user),
            lambda: delete_status(self.project, option.pk),
        ])
        self.assertEqual(outcomes.count(200), 1, outcomes)
        self.assertIn(outcomes, ([200, 409], [400, 200]))
        document.refresh_from_db()
        self.assertTrue(DocumentStatus.objects.filter(project=self.project, value=document.status).exists())

    def test_competing_creates_produce_one_option(self):
        outcomes = self.race([
            lambda: create_status(self.project, "Same status"),
            lambda: create_status(self.project, "SAME STATUS"),
        ])
        self.assertCountEqual(outcomes, [200, 409])
        self.assertEqual(DocumentStatus.objects.filter(project=self.project, value="same_status").count(), 1)

    def test_import_and_delete_never_remove_an_imported_current_status(self):
        from io import BytesIO
        import pandas as pd
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIClient
        from orgs.models import ProjectRoleAssignment

        option = create_status(self.project, "Imported Review")
        ProjectRoleAssignment.objects.create(project=self.project, user=self.user,
                                            domain="compliance", role="manager")
        output = BytesIO()
        pd.DataFrame([{"Document Name": "Document", "Cover Page Number": "CP-S", "Status": "Imported Review"}]).to_excel(output, index=False)
        def upload():
            return SimpleUploadedFile("statuses.xlsx", output.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        base = "/api/projects/ozgur/compliance-documents/"
        client = APIClient()
        client.force_authenticate(self.user)
        preview = client.post(base + "imports/preview/", {"file": upload()}, format="multipart")
        self.assertEqual(preview.status_code, 200)
        def confirm():
            worker = APIClient()
            worker.force_authenticate(self.user)
            response = worker.post(base + "imports/confirm/", {
                "file": upload(), "confirmation_token": preview.data["confirmation_token"],
            }, format="multipart")
            self.assertEqual(response.status_code, 201, response.data)
        outcomes = self.race([confirm, lambda: delete_status(self.project, option.pk)])
        self.assertEqual(outcomes[0], 200)
        self.assertIn(outcomes[1], (200, 409))
        document = ComplianceDocument.objects.get(project=self.project)
        self.assertEqual(document.status, "imported_review")
        self.assertTrue(DocumentStatus.objects.filter(project=self.project, value=document.status).exists())
