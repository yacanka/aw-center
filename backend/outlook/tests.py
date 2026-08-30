"""Canonical Outlook message inspection API tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from jobs.contracts import JobExecutionFailure
from jobs.tests.base import JobTestCase
from jobs.tests.test_outlook_jobs import FakeAttachment, FakeMessage
from jobs.tests.test_outlook_workflows import outlook_upload
from outlook.views import (
    CACHE_SECONDS,
    cache_attachments,
    cache_key,
    consume_attachment_capability,
)


class OutlookMessageApiTests(JobTestCase):
    def tearDown(self):
        cache.clear()
        super().tearDown()

    @patch("outlook.views.open_message")
    def test_parse_returns_plain_text_and_post_download_capability(self, open_message_mock):
        message = FakeMessage([FakeAttachment("report.txt", b"safe evidence")])
        message.subject = "Review"
        message.sender = "sender@example.test"
        message.to = "recipient@example.test"
        message.cc = ""
        message.date = "2026-07-19"
        message.body = "<script>alert('unsafe')</script>"
        open_message_mock.return_value = message

        response = self.client.post(
            "/api/tools/outlook/msg/parse/",
            {"file": outlook_upload(), "inline": "true"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("body_html", response.data["mail"])
        self.assertEqual(response.data["mail"]["body_plain"], message.body)
        attachment = response.data["attachments"][0]
        self.assertNotIn("content_base64", attachment)
        self.assertNotIn("download_url", attachment)
        self.assertEqual(len(attachment["download_capability"]), 48)

    @patch("outlook.views.open_message")
    def test_attachment_link_is_bound_to_parsing_user(self, open_message_mock):
        message = FakeMessage([FakeAttachment("report.txt", b"private evidence")])
        message.subject = message.sender = message.to = message.cc = message.date = message.body = ""
        open_message_mock.return_value = message
        parsed = self.client.post(
            "/api/tools/outlook/msg/parse/",
            {"file": outlook_upload()},
            format="multipart",
        )
        capability = parsed.data["attachments"][0]["download_capability"]
        payload = {"capability": capability}

        self.client.force_authenticate(self.other_user)
        denied = self.client.post("/api/tools/outlook/msg/download/", payload, format="json")
        self.client.force_authenticate(self.user)
        allowed = self.client.post("/api/tools/outlook/msg/download/", payload, format="json")
        replay = self.client.post("/api/tools/outlook/msg/download/", payload, format="json")

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.content, b"private evidence")
        self.assertEqual(allowed["X-Content-Type-Options"], "nosniff")
        self.assertEqual(replay.status_code, 404)

    @patch("outlook.views.open_message")
    def test_attachment_download_rejects_cache_tampering(self, open_message_mock):
        message = FakeMessage([FakeAttachment("report.txt", b"verified evidence")])
        message.subject = message.sender = message.to = message.cc = message.date = message.body = ""
        open_message_mock.return_value = message
        parsed = self.client.post(
            "/api/tools/outlook/msg/parse/",
            {"file": outlook_upload()},
            format="multipart",
        )
        capability = parsed.data["attachments"][0]["download_capability"]
        package = cache.get(cache_key(capability))
        package["attachment"]["bytes"] = b"tampered evidence"
        cache.set(cache_key(capability), package, CACHE_SECONDS)

        response = self.client.post(
            "/api/tools/outlook/msg/download/",
            {"capability": capability},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "OUTLOOK_ATTACHMENT_INTEGRITY_FAILED")
        self.assertIsNone(cache.get(cache_key(capability)))

    def test_attachment_capability_has_one_winner_under_concurrent_consumption(self):
        capability = cache_attachments(
            self.user.pk,
            [{"name": "report.txt", "mime": "text/plain", "bytes": b"private"}],
        )[0]
        barrier = Barrier(2)

        def consume():
            barrier.wait()
            return consume_attachment_capability(capability, self.user.pk)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: consume(), range(2)))

        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertIsNone(cache.get(cache_key(capability)))

    @patch("outlook.views.open_message")
    def test_parser_failure_does_not_disclose_internal_exception(self, open_message_mock):
        open_message_mock.side_effect = JobExecutionFailure(
            "The Outlook message could not be read.", "OUTLOOK_MESSAGE_INVALID"
        )

        response = self.client.post(
            "/api/tools/outlook/msg/parse/",
            {"file": outlook_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("private", str(response.data).lower())

    @override_settings(OUTLOOK_PARSE_RATE="1/hour")
    @patch("outlook.views.open_message")
    def test_message_parsing_is_rate_limited_per_user(self, open_message_mock):
        message = FakeMessage([])
        message.subject = message.sender = message.to = message.cc = message.date = message.body = ""
        open_message_mock.return_value = message

        first = self.client.post(
            "/api/tools/outlook/msg/parse/",
            {"file": outlook_upload()},
            format="multipart",
        )
        second = self.client.post(
            "/api/tools/outlook/msg/parse/",
            {"file": outlook_upload()},
            format="multipart",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
