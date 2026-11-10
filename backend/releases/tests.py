import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ReleaseNote, ReleaseNoteSeen


BULK_SEEN_URL = "/api/releases/release-notes/bulk-seen"
UNSEEN_URL = "/api/releases/release-notes/unseen"


class RequiredAcknowledgementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ack-reader")
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_seen_required_note_remains_pending_until_acknowledged(self):
        note = ReleaseNote.objects.create(version="1.0", title="Required", requires_ack=True)
        for url, payload in (
            (f"/api/releases/release-notes/{note.id}/seen", {}),
            (BULK_SEEN_URL, {"ids": [note.id]}),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, payload, format="json").status_code, 200)
                self.assertIsNone(ReleaseNoteSeen.objects.get(
                    user=self.user, release_note=note
                ).acknowledged_at)

                reloaded = self.client.get(UNSEEN_URL)

                self.assertEqual(reloaded.status_code, 200)
                self.assertEqual(reloaded.data["latest"]["id"], note.id)

        self.assertEqual(self.client.post(
            f"/api/releases/release-notes/{note.id}/ack", {}, format="json"
        ).status_code, 200)
        self.assertEqual(self.client.get(UNSEEN_URL).status_code, 204)

    def test_required_notes_are_presented_before_ordinary_notes_and_acknowledged_in_order(self):
        # Windows can publish several notes within one clock tick.
        with patch("django.utils.timezone.now", return_value=timezone.now()):
            first = ReleaseNote.objects.create(version="1.0", title="First", requires_ack=True)
            second = ReleaseNote.objects.create(version="1.1", title="Second", requires_ack=True)
            ordinary = ReleaseNote.objects.create(version="1.2", title="Ordinary")
            latest = ReleaseNote.objects.create(version="1.3", title="Latest ordinary")

        for note in (second, first):
            response = self.client.get(UNSEEN_URL)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["latest"]["id"], note.id)
            self.assertEqual(response.data["mark_seen_ids"], [note.id])
            self.client.post(BULK_SEEN_URL, {"ids": response.data["mark_seen_ids"]}, format="json")
            self.assertEqual(self.client.get(UNSEEN_URL).data["latest"]["id"], note.id)
            self.client.post(f"/api/releases/release-notes/{note.id}/ack", {}, format="json")

        remaining = self.client.get(UNSEEN_URL)
        self.assertEqual(remaining.data["latest"]["id"], latest.id)
        self.assertEqual(remaining.data["mark_seen_ids"], [latest.id, ordinary.id])
        self.client.post(BULK_SEEN_URL, {"ids": remaining.data["mark_seen_ids"]}, format="json")
        self.assertEqual(self.client.get(UNSEEN_URL).status_code, 204)

    def test_other_users_acknowledgements_do_not_hide_required_notes(self):
        note = ReleaseNote.objects.create(version="1.0", title="Required", requires_ack=True)
        other = get_user_model().objects.create_user(username="other-ack-reader")
        ReleaseNoteSeen.objects.create(
            user=other, release_note=note, acknowledged_at=timezone.now()
        )

        response = self.client.get(UNSEEN_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["latest"]["id"], note.id)

    def test_inactive_required_notes_are_not_presented(self):
        ReleaseNote.objects.create(
            version="1.0", title="Inactive", requires_ack=True, is_active=False
        )

        self.assertEqual(self.client.get(UNSEEN_URL).status_code, 204)


class BulkSeenTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="release-reader")
        self.other_user = get_user_model().objects.create_user(username="other-reader")
        self.note = ReleaseNote.objects.create(version="1.0", title="First release")
        self.other_note = ReleaseNote.objects.create(version="1.1", title="Second release")
        self.inactive_note = ReleaseNote.objects.create(
            version="0.9", title="Inactive release", is_active=False
        )
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_repeated_ids_and_requests_only_count_new_active_notes(self):
        seen = ReleaseNoteSeen.objects.create(
            user=self.user, release_note=self.note, acknowledged_at=timezone.now()
        )
        original_seen_at = seen.seen_at
        original_acknowledged_at = seen.acknowledged_at
        payload = {
            "ids": [
                self.note.id, self.other_note.id, self.other_note.id,
                self.inactive_note.id, 9223372036854775807,
            ]
        }

        response = self.client.post(BULK_SEEN_URL, payload, format="json")
        repeated = self.client.post(BULK_SEEN_URL, payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"ok": True, "created": 1})
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.data, {"ok": True, "created": 0})
        self.assertEqual(
            set(ReleaseNoteSeen.objects.filter(user=self.user).values_list(
                "release_note_id", flat=True
            )),
            {self.note.id, self.other_note.id},
        )
        seen.refresh_from_db()
        self.assertEqual(seen.seen_at, original_seen_at)
        self.assertEqual(seen.acknowledged_at, original_acknowledged_at)

    def test_existing_seen_rows_are_scoped_to_the_session_user(self):
        ReleaseNoteSeen.objects.create(user=self.other_user, release_note=self.note)

        response = self.client.post(
            BULK_SEEN_URL, {"ids": [self.note.id], "user": self.other_user.id}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"ok": True, "created": 1})
        self.assertTrue(ReleaseNoteSeen.objects.filter(
            user=self.user, release_note=self.note
        ).exists())
        self.assertEqual(ReleaseNoteSeen.objects.filter(user=self.other_user).count(), 1)

    def test_missing_or_empty_ids_are_successful_noops(self):
        for payload in ({}, {"ids": []}):
            with self.subTest(payload=payload):
                response = self.client.post(BULK_SEEN_URL, payload, format="json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, {"ok": True, "created": 0})
        self.assertFalse(ReleaseNoteSeen.objects.exists())

    def test_invalid_ids_return_validation_error_without_writes(self):
        invalid_values = [
            None, False, 1, "1", {}, [True], [False], [1.5], [1.0],
            ["1"], [{}], [[]], [None], [0], [-1], [9223372036854775808],
        ]
        for value in invalid_values:
            with self.subTest(ids=value):
                response = self.client.post(BULK_SEEN_URL, {"ids": value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "VALIDATION_ERROR")
                self.assertIn("ids", response.data["errors"])
                self.assertFalse(ReleaseNoteSeen.objects.exists())

    def test_non_object_payloads_return_validation_error(self):
        for payload in ([], [self.note.id], "ids", 1, None):
            with self.subTest(payload=payload):
                response = self.client.generic(
                    "POST", BULK_SEEN_URL,
                    data=json.dumps(payload), content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.assertFalse(ReleaseNoteSeen.objects.exists())

    def test_list_limit_is_applied_before_duplicate_elimination(self):
        accepted = self.client.post(
            BULK_SEEN_URL, {"ids": [self.note.id] * 1000}, format="json"
        )
        rejected = self.client.post(
            BULK_SEEN_URL, {"ids": [self.other_note.id] * 1001}, format="json"
        )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data, {"ok": True, "created": 1})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.data["code"], "VALIDATION_ERROR")
        self.assertFalse(ReleaseNoteSeen.objects.filter(release_note=self.other_note).exists())

    def test_oversized_invalid_list_returns_one_size_error(self):
        response = self.client.post(
            BULK_SEEN_URL, {"ids": [None] * 1001}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        errors = response.data["errors"]["ids"]
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors, list)
        self.assertFalse(ReleaseNoteSeen.objects.exists())

    def test_anonymous_request_cannot_mark_notes_seen(self):
        self.client.logout()
        response = self.client.post(BULK_SEEN_URL, {"ids": [self.note.id]}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ReleaseNoteSeen.objects.exists())

    @override_settings(SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
    def test_authenticated_session_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        bootstrap = client.get("/api/session/")
        token = bootstrap.cookies["csrftoken"].value

        rejected = client.post(BULK_SEEN_URL, {"ids": [self.note.id]}, format="json")
        self.assertEqual(rejected.status_code, 403)
        self.assertFalse(ReleaseNoteSeen.objects.exists())

        accepted = client.post(
            BULK_SEEN_URL, {"ids": [self.note.id]}, format="json", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data, {"ok": True, "created": 1})


@override_settings(SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class BulkSeenConcurrencyTests(TransactionTestCase):
    def test_concurrent_requests_create_each_note_once_with_exact_counts(self):
        user = get_user_model().objects.create_user(username="concurrent-reader")
        notes = [
            ReleaseNote.objects.create(version="2.0", title="Concurrent first"),
            ReleaseNote.objects.create(version="2.1", title="Concurrent second"),
        ]
        clients = []
        for _ in range(2):
            client = APIClient(enforce_csrf_checks=True)
            client.force_login(user)
            token = client.get("/api/session/").cookies["csrftoken"].value
            clients.append((client, token))

        request_barrier = Barrier(2)
        stale_read_barrier = Barrier(2)

        def post_seen(client_and_token):
            client, token = client_and_token
            synchronized = False

            def synchronize_autocommit_seen_read(execute, sql, params, many, context):
                nonlocal synchronized
                result = execute(sql, params, many, context)
                # Reproduce the original stale pre-check with real SQL. An atomic
                # SQLite writer must acquire IMMEDIATE before reading, so waiting
                # on a second reader inside that transaction would deadlock.
                if (not synchronized and sql.lstrip().upper().startswith("SELECT")
                        and '"releases_releasenoteseen"' in sql
                        and not context["connection"].in_atomic_block):
                    synchronized = True
                    stale_read_barrier.wait(timeout=10)
                return result

            try:
                with connection.execute_wrapper(synchronize_autocommit_seen_read):
                    request_barrier.wait(timeout=10)
                    response = client.post(
                        BULK_SEEN_URL,
                        {"ids": [notes[1].id, notes[0].id, notes[1].id]},
                        format="json", HTTP_X_CSRFTOKEN=token,
                    )
                    return response.status_code, response.data
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(post_seen, clients))

        self.assertEqual([status for status, _ in responses], [200, 200], responses)
        self.assertTrue(all(data["ok"] for _, data in responses))
        self.assertEqual(sum(data["created"] for _, data in responses), 2)
        self.assertEqual(
            set(ReleaseNoteSeen.objects.filter(user=user).values_list("release_note_id", flat=True)),
            {notes[0].id, notes[1].id},
        )
        self.assertEqual(ReleaseNoteSeen.objects.filter(user=user).count(), 2)
