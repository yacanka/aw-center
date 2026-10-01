"""Real database regression for competing compliance catalog imports."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from orgs.models import Panel, Project, ProjectRoleAssignment

from .models import ComplianceDocument, ImportAudit


class ImportConcurrencyTests(TransactionTestCase):
    def test_competing_confirmations_do_not_overwrite_a_new_panel(self):
        project, _ = Project.objects.get_or_create(slug="ozgur", defaults={"name": "Ozgur"})
        user = get_user_model().objects.create_user("concurrent-import-editor")
        ProjectRoleAssignment.objects.create(
            project=project,
            user=user,
            domain=ProjectRoleAssignment.Domain.COMPLIANCE,
            role=ProjectRoleAssignment.Role.EDITOR,
        )
        client = APIClient()
        client.force_authenticate(user)
        reviewed = []
        for name in ("First proposal", "Second proposal"):
            output = BytesIO()
            pd.DataFrame([{
                "Document Name": name, "Cover Page Number": "CP-P", "Panel": name, "ATA Chapter": "29",
            }]).to_excel(output, index=False)
            content = output.getvalue()
            response = client.post(
                "/api/projects/ozgur/compliance-documents/imports/preview/",
                {"file": self.upload(content)}, format="multipart",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["created_count"], 1)
            reviewed.append((name, content, response.data["confirmation_token"]))
        self.assertFalse(Panel.objects.filter(project=project).exists())
        start = Barrier(2)

        def confirm(proposal):
            name, content, token = proposal
            try:
                worker_client = APIClient()
                worker_client.force_authenticate(user)
                start.wait(timeout=10)
                response = worker_client.post(
                    "/api/projects/ozgur/compliance-documents/imports/confirm/",
                    {"file": self.upload(content), "confirmation_token": token},
                    format="multipart",
                )
                return name, response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(confirm, reviewed, timeout=45))

        self.assertCountEqual([status for _, status in outcomes], [201, 409])
        winning_name = next(name for name, status in outcomes if status == 201)
        panel = Panel.objects.get(project=project, ata="29-00")
        self.assertEqual(panel.name, winning_name)
        document = ComplianceDocument.objects.get(project=project)
        self.assertEqual(document.name, winning_name)
        self.assertEqual(document.panel_id, panel.pk)
        self.assertCountEqual(
            ImportAudit.objects.values_list("status", flat=True),
            [ImportAudit.Status.SUCCESS, ImportAudit.Status.FAILED],
        )

    @staticmethod
    def upload(content):
        return SimpleUploadedFile(
            "compliance.xlsx", content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
