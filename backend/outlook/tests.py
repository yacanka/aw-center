"""Canonical Outlook message inspection API tests."""

from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from unittest.mock import patch

from django.core.cache import cache
from django.core.cache.backends.filebased import FileBasedCache
from django.test import SimpleTestCase, override_settings

from awcenter.cache_locks import cache_entry_lock
from jobs.contracts import JobExecutionFailure
from jobs.tests.base import JobTestCase
from jobs.tests.test_outlook_jobs import FakeAttachment, FakeMessage
from jobs.tests.test_outlook_workflows import outlook_upload
from outlook.test_helpers import consume_file_cache_in_process, synchronized_file_cache_reads
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


class OutlookFileCacheCapabilityTests(SimpleTestCase):
    """Exercise single-use downloads against the Windows production cache backend."""

    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory(prefix="outlook-cache-test-"))
        self.enterContext(override_settings(CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                "LOCATION": self.directory,
            },
        }))
        self.owner_id = 17
        self.capability = cache_attachments(
            self.owner_id,
            [{"name": "report.txt", "mime": "text/plain", "bytes": b"private"}],
        )[0]

    def test_concurrent_file_cache_readers_have_only_one_successful_consumption(self):
        read_barrier = Barrier(2)
        add_barrier = Barrier(2)
        key = cache_key(self.capability)
        with (
            synchronized_file_cache_reads(key, read_barrier, add_barrier),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            results = list(executor.map(
                lambda _index: consume_attachment_capability(self.capability, self.owner_id),
                range(2),
            ))

        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertIsNone(cache.get(key))

    def test_payload_is_not_returned_when_cache_deletion_does_not_succeed(self):
        with patch.object(FileBasedCache, "delete", return_value=False):
            result = consume_attachment_capability(self.capability, self.owner_id)

        self.assertIsNone(result)

    def test_separate_processes_have_only_one_successful_consumption(self):
        context = get_context("spawn")
        results = context.Queue()
        read_barrier, add_barrier = context.Barrier(2), context.Barrier(2)
        processes = [
            context.Process(target=consume_file_cache_in_process, args=(
                self.directory, self.capability, self.owner_id, read_barrier, add_barrier, results,
            ))
            for _index in range(2)
        ]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)
                self.assertFalse(process.is_alive(), "Capability consumer did not finish.")
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sum(results.get(timeout=5) for _index in range(2)), 1)
            self.assertIsNone(cache.get(cache_key(self.capability)))
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                process.close()
            results.close()
            results.join_thread()

    def test_wrong_owner_does_not_consume_the_capability(self):
        self.assertIsNone(consume_attachment_capability(self.capability, self.owner_id + 1))
        package = consume_attachment_capability(self.capability, self.owner_id)
        self.assertEqual(package["attachment"]["bytes"], b"private")

    def test_expired_capability_cannot_be_consumed(self):
        cache.touch(cache_key(self.capability), timeout=-1)
        self.assertIsNone(consume_attachment_capability(self.capability, self.owner_id))

    def test_capability_expiring_while_waiting_for_lock_cannot_be_consumed(self):
        read_finished = Event()
        original_get = FileBasedCache.get
        key = cache_key(self.capability)

        def signal_payload_read(backend, requested_key, *args, **kwargs):
            package = original_get(backend, requested_key, *args, **kwargs)
            if requested_key == key:
                read_finished.set()
            return package

        with (
            patch.object(FileBasedCache, "get", signal_payload_read),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            with cache_entry_lock(key) as acquired:
                self.assertTrue(acquired)
                result = executor.submit(
                    consume_attachment_capability, self.capability, self.owner_id,
                )
                self.assertTrue(read_finished.wait(timeout=5))
                cache.touch(key, timeout=-1)
            self.assertIsNone(result.result(timeout=5))

    def test_malformed_capabilities_cannot_be_consumed(self):
        for capability in ("", "short", "/" * 48, "A" * 49):
            with self.subTest(capability=capability):
                self.assertIsNone(consume_attachment_capability(capability, self.owner_id))

    @patch("awcenter.cache_locks.locks.lock", return_value=False)
    @patch("awcenter.cache_locks.monotonic", side_effect=[0, 3])
    def test_lock_timeout_does_not_expose_or_consume_payload(self, _clock, _lock):
        self.assertIsNone(consume_attachment_capability(self.capability, self.owner_id))
        self.assertIsNotNone(cache.get(cache_key(self.capability)))

    @patch("awcenter.cache_locks.os.open", side_effect=PermissionError)
    def test_lock_creation_failure_does_not_expose_or_consume_payload(self, _open):
        self.assertIsNone(consume_attachment_capability(self.capability, self.owner_id))
        self.assertIsNotNone(cache.get(cache_key(self.capability)))


class OutlookFileCacheMessageApiTests(OutlookMessageApiTests):
    """Apply owner, replay, integrity, and parse tests to the production cache backend."""

    def setUp(self):
        super().setUp()
        directory = self.enterContext(TemporaryDirectory(prefix="outlook-api-cache-test-"))
        self.enterContext(override_settings(CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                "LOCATION": directory,
            },
        }))
