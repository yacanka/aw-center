"""Acceptance tests for the first-production ingress smoke command."""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from docx import Document

from compliance.models import ComplianceDocument, ImportAudit
from dcc.models import DccRecord
from jobs.models import Job, WorkerHeartbeat
from orgs.models import Project
from users.models import PasswordResetDelivery


class ReleaseSmokeTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_superuser(
            username="release-operator",
            email="operator@example.invalid",
            password="StrongPass!123",
        )

    def test_core_stage_exercises_contracts_and_removes_ephemeral_state(self):
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "hys_dcc_template.docx"
            document = Document()
            document.add_paragraph("{{ Design_Change_Title }}")
            document.save(template)
            output = StringIO()
            with patch(
                "dcc.document_job.resolve_dcc_template_path",
                return_value=template,
            ):
                call_command(
                    "run_release_smoke",
                    stage="core",
                    operator_username=self.operator.username,
                    project="hys",
                    confirm_fresh_install=True,
                    stdout=output,
                )

        self.assertIn("Release smoke passed", output.getvalue())
        self.assertFalse(ComplianceDocument.objects.exists())
        self.assertFalse(ImportAudit.objects.exists())
        self.assertFalse(Job.objects.exists())
        self.assertFalse(WorkerHeartbeat.objects.filter(worker_id__startswith="release-smoke-").exists())
        self.assertFalse(get_user_model().objects.filter(username__startswith="release-smoke-").exists())

    @override_settings(
        AWCENTER_MAIL_TRANSPORT="django",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="no-reply@example.invalid",
        FRONTEND_RESET_URL="https://awcenter.example.invalid/app/login",
    )
    def test_notification_stage_delivers_from_worker_boundary_and_cleans_up(self):
        output = StringIO()

        call_command(
            "run_release_smoke",
            stage="notification",
            operator_username=self.operator.username,
            notification_recipient="release-canary@example.invalid",
            confirm_fresh_install=True,
            stdout=output,
        )

        self.assertIn("notification=passed", output.getvalue())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Message-ID", mail.outbox[0].extra_headers)
        self.assertFalse(PasswordResetDelivery.objects.exists())
        self.assertFalse(
            get_user_model().objects.filter(username__startswith="release-mail-smoke-").exists()
        )

    def test_requires_explicit_fresh_install_confirmation(self):
        with self.assertRaises(CommandError):
            call_command(
                "run_release_smoke",
                stage="core",
                operator_username=self.operator.username,
            )

    def test_refuses_to_run_against_existing_business_state(self):
        project = Project.objects.get(slug="hys")
        DccRecord.objects.create(
            issue="AW-EXISTING",
            title="Existing production state",
            owner=self.operator,
        ).projects.add(project)

        with self.assertRaisesRegex(CommandError, "unused database"):
            call_command(
                "run_release_smoke",
                stage="core",
                operator_username=self.operator.username,
                project="hys",
                confirm_fresh_install=True,
            )
