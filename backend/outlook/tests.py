from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from jobs.contracts import JobExecutionFailure
from jobs.tests.base import JobTestCase
from jobs.tests.test_outlook_jobs import FakeAttachment, FakeMessage
from jobs.tests.test_outlook_workflows import outlook_upload


class OutlookMessageApiTests(JobTestCase):
    """Verify safe message rendering and owner-bound attachment downloads."""

    def tearDown(self):
        """Clear temporary attachment tokens after each test."""

        cache.clear()
        super().tearDown()

    @patch("outlook.views.open_message")
    def test_parse_returns_plain_text_and_no_embedded_bytes(self, open_message_mock):
        """Untrusted message HTML and base64 attachment bodies never reach the SPA."""

        message = FakeMessage([FakeAttachment("report.txt", b"safe evidence")])
        message.subject = "Review"
        message.sender = "sender@example.test"
        message.to = "recipient@example.test"
        message.cc = ""
        message.date = "2026-07-19"
        message.body = "<script>alert('unsafe')</script>"
        open_message_mock.return_value = message

        response = self.client.post(
            "/outlook/msg/parse/", {"file": outlook_upload(), "inline": "true"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("body_html", response.data["mail"])
        self.assertEqual(response.data["mail"]["body_plain"], message.body)
        self.assertNotIn("content_base64", response.data["attachments"][0])
        self.assertIn("download_url", response.data["attachments"][0])

    @patch("outlook.views.open_message")
    def test_attachment_link_is_bound_to_parsing_user(self, open_message_mock):
        """A valid high-entropy token cannot cross the authenticated owner boundary."""

        message = FakeMessage([FakeAttachment("report.txt", b"private evidence")])
        message.subject = message.sender = message.to = message.cc = message.date = message.body = ""
        open_message_mock.return_value = message
        parsed = self.client.post(
            "/outlook/msg/parse/", {"file": outlook_upload()}, format="multipart"
        )
        url = parsed.data["attachments"][0]["download_url"]

        self.client.force_authenticate(self.other_user)
        denied = self.client.get(url)
        self.client.force_authenticate(self.user)
        allowed = self.client.get(url)

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.content, b"private evidence")
        self.assertEqual(allowed["X-Content-Type-Options"], "nosniff")

    @patch("outlook.views.open_message")
    def test_parser_failure_does_not_disclose_internal_exception(self, open_message_mock):
        """Parser internals are replaced with a stable validation response."""

        open_message_mock.side_effect = JobExecutionFailure(
            "The Outlook message could not be read.", "OUTLOOK_MESSAGE_INVALID"
        )

        response = self.client.post(
            "/outlook/msg/parse/", {"file": outlook_upload()}, format="multipart"
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("private", str(response.data).lower())

    @override_settings(OUTLOOK_PARSE_RATE="1/hour")
    @patch("outlook.views.open_message")
    def test_message_parsing_is_rate_limited_per_user(self, open_message_mock):
        """Repeated cache-producing parses are bounded for each authenticated user."""

        message = FakeMessage([])
        message.subject = message.sender = message.to = message.cc = message.date = message.body = ""
        open_message_mock.return_value = message

        first = self.client.post(
            "/outlook/msg/parse/", {"file": outlook_upload()}, format="multipart"
        )
        second = self.client.post(
            "/outlook/msg/parse/", {"file": outlook_upload()}, format="multipart"
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    @patch("dcc.views.resolve_effectivity_value", return_value="")
    @patch("dcc.views.resolve_project_from_jira_components")
    @patch("dcc.views.JiraConnector")
    @patch("dcc.views.safe_ecd_parse")
    @patch("outlook.views.open_message")
    def test_pdf_attachment_reaches_parser_issue_and_attachment_endpoints(
        self,
        open_message_mock,
        parse_mock,
        jira_connector_mock,
        project_resolver_mock,
        _effectivity_mock,
    ):
        """Preserve PDF bytes through MSG download, parsing, issue creation, and attach."""

        pdf_bytes = b"%PDF-1.4\nvalidated-ecr"
        open_message_mock.return_value = outlook_message(pdf_bytes)
        parse_mock.return_value = parsed_ecr()
        project_resolver_mock.return_value = SimpleNamespace(
            jira_component="AW Center", dcc_label="AW"
        )
        jira_issue = SimpleNamespace(
            key="CHN-42", fields=SimpleNamespace(summary="Validated change")
        )
        jira_client = jira_connector_mock.return_value
        jira_client.create_issue.return_value = jira_issue
        attached_bytes = []
        jira_client.add_attachment.side_effect = lambda file, **_: attached_bytes.append(file.read())
        self.user.user_permissions.add(Permission.objects.get(codename="add_jira_dcc"))

        parsed_message = self.client.post(
            "/outlook/msg/parse/", {"file": outlook_upload()}, format="multipart"
        )
        downloaded = self.client.get(parsed_message.data["attachments"][0]["download_url"])
        parser_response = self.client.post(
            "/dcc/upload/",
            {
                "file": SimpleUploadedFile("change.pdf", downloaded.content, "application/pdf"),
                "JSESSIONID": "transient-session",
            },
            format="multipart",
        )
        create_response = self.client.post(
            "/dcc/create_issue/",
            {**parser_response.data, "JSESSIONID": "transient-session"},
            format="json",
        )
        attach_response = self.client.post(
            "/dcc/add_attachment/",
            {
                "file": SimpleUploadedFile("change.pdf", downloaded.content, "application/pdf"),
                "JSESSIONID": "transient-session",
                "issue_key": create_response.data["issue"],
            },
            format="multipart",
        )

        self.assertEqual([parsed_message.status_code, parser_response.status_code], [200, 200])
        self.assertEqual([create_response.status_code, attach_response.status_code], [201, 201])
        self.assertEqual(downloaded.content, pdf_bytes)
        self.assertEqual(attached_bytes, [pdf_bytes])


def outlook_message(pdf_bytes):
    """Return a complete fake Outlook message containing one PDF attachment."""

    message = FakeMessage([FakeAttachment("change.pdf", pdf_bytes)])
    message.subject = "CRB 42 Call"
    message.sender = "sender@example.test"
    message.to = "recipient@example.test"
    message.cc = message.date = message.body = ""
    return message


def parsed_ecr():
    """Return the minimum parsed ECR contract consumed by legacy JIRA creation."""

    return {
        "ecd_no": "ECD-42 / REV-A",
        "ecd_title": "Validated change",
        "project": "AW Center",
        "requestor": "Requestor",
        "effectivity": "",
    }
