"""Outlook MSG draft generation and CompDoc download tests."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common import compdoc_msg_draft
from common.compdoc_import_test_utils import grant_model_permissions
from common.compdoc_msg_draft import (
    MsgDraftInputError,
    MsgDraftUnavailable,
    build_msg_draft,
)
from common.compdoc_tracking_models import CompDocTrackingProfile
from orgs.models import People
from projects.ozgur.models import CompDoc, Panel, Responsible


class FakeMailItem:
    """Capture Outlook fields and emit a minimal OLE-signature fixture."""

    def SaveAs(self, path, file_type):
        """Record the Unicode MSG request and create its expected output."""

        self.saved_path = path
        self.saved_type = file_type
        Path(path).write_bytes(compdoc_msg_draft.OLE_SIGNATURE + b"draft")


class FakeOutlookApplication:
    """Return one observable fake Outlook mail item."""

    def __init__(self, mail_item):
        self.mail_item = mail_item
        self.item_type = None

    def CreateItem(self, item_type):
        """Capture the requested Outlook item type."""

        self.item_type = item_type
        return self.mail_item


class FakePythonCom:
    """Track balanced COM thread initialization."""

    def __init__(self):
        self.initialized = 0
        self.uninitialized = 0

    def CoInitialize(self):
        """Record COM initialization."""

        self.initialized += 1

    def CoUninitialize(self):
        """Record COM cleanup."""

        self.uninitialized += 1


class MsgDraftServiceTests(SimpleTestCase):
    """Verify Unicode Outlook draft fields, integrity, and cleanup."""

    def test_builds_editable_unicode_msg_without_sending(self):
        mail_item = FakeMailItem()
        application = FakeOutlookApplication(mail_item)
        python_com = FakePythonCom()
        dispatch = lambda program_id: application
        win32 = SimpleNamespace(client=SimpleNamespace(Dispatch=dispatch))

        with (
            patch.object(compdoc_msg_draft, "pythoncom", python_com),
            patch.object(compdoc_msg_draft, "win32com", win32),
        ):
            content = build_msg_draft("Subject", "<p>Body</p>", ["b@test.dev", "a@test.dev"])

        self.assertTrue(content.startswith(compdoc_msg_draft.OLE_SIGNATURE))
        self.assertEqual(mail_item.Subject, "Subject")
        self.assertEqual(mail_item.To, "a@test.dev;b@test.dev")
        self.assertEqual(mail_item.CC, "")
        self.assertEqual(mail_item.BodyFormat, compdoc_msg_draft.OL_FORMAT_HTML)
        self.assertEqual(mail_item.HTMLBody, "<p>Body</p>")
        self.assertEqual(mail_item.saved_type, compdoc_msg_draft.OL_MSG_UNICODE)
        self.assertFalse(Path(mail_item.saved_path).exists())
        self.assertEqual((python_com.initialized, python_com.uninitialized), (1, 1))

    def test_rejects_recipient_injection_before_outlook_access(self):
        with self.assertRaises(MsgDraftInputError):
            build_msg_draft("Subject", "<p>Body</p>", ["safe@test.dev;other@test.dev"])

    @patch.object(compdoc_msg_draft, "pythoncom", None)
    @patch.object(compdoc_msg_draft, "win32com", None)
    def test_reports_outlook_unavailability(self):
        with self.assertRaises(MsgDraftUnavailable):
            build_msg_draft("Subject", "<p>Body</p>", ["safe@test.dev"])


class CompDocMsgDraftApiTests(TestCase):
    """Verify permission-protected template-backed draft downloads."""

    def setUp(self):
        """Create one overdue tracked document and automatic ATA recipient."""

        self.user = get_user_model().objects.create_user("draft-user", password="Pass!123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        panel = Panel.objects.create(name="Flight", discipline="Systems", ata="21-00")
        person = People.objects.create(
            person_id="100004", name="Dorothy Vaughan", email="dorothy@example.com"
        )
        Responsible.objects.create(
            panel=panel,
            person=person,
            title="CVE",
        )
        target = timezone.localdate() - timedelta(days=2)
        self.document = CompDoc.objects.create(
            name="Draft Manual",
            cover_page_no="CP-DRAFT",
            tech_doc_no="TD/42",
            ata="21-00",
            status_flow=[{"status": "to_be_issued", "date": target.isoformat()}],
        )
        CompDocTrackingProfile.objects.create(
            project_slug="ozgur",
            document_id=self.document.pk,
        )
        self.path = f"/ozgur/compdocs/{self.document.pk}/notifications/draft/"

    @patch("common.compdoc_tracking_views.build_msg_draft")
    def test_download_contains_shared_template_fields(self, builder):
        builder.return_value = compdoc_msg_draft.OLE_SIGNATURE + b"draft"
        grant_model_permissions(self.user, CompDoc, "change")

        response = self.client.post(self.path, {"event_type": "overdue"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.ms-outlook")
        self.assertIn('filename="ozgur-TD-42-overdue.msg"', response["Content-Disposition"])
        content = builder.call_args.args
        self.assertEqual(content[2], ["dorothy@example.com"])
        self.assertEqual(content[3], [])
        self.assertIn("Draft Manual", content[0])
        self.assertIn("<strong>Draft Manual</strong>", content[1])

    def test_download_requires_change_permission(self):
        response = self.client.post(self.path, {"event_type": "overdue"}, format="json")

        self.assertEqual(response.status_code, 403)

    @patch("common.compdoc_tracking_views.build_msg_draft")
    def test_download_rejects_an_event_without_current_evidence(self, builder):
        grant_model_permissions(self.user, CompDoc, "change")

        response = self.client.post(
            self.path,
            {"event_type": "revision_available"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "COMPDOC_NOTIFICATION_NOT_APPLICABLE")
        builder.assert_not_called()

    @patch(
        "common.compdoc_tracking_views.build_msg_draft",
        side_effect=MsgDraftUnavailable,
    )
    def test_unavailable_outlook_returns_actionable_error(self, _builder):
        grant_model_permissions(self.user, CompDoc, "change")

        response = self.client.post(self.path, {"event_type": "overdue"}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "COMPDOC_MSG_DRAFT_UNAVAILABLE")
        self.assertIn("Outlook", response.data["recovery_hint"])
