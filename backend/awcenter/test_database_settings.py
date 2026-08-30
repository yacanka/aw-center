"""Database configuration regression tests."""

import sqlite3
import tempfile
from pathlib import Path
from threading import Event, Thread

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from awcenter.settings import configure_sqlite_concurrency


class SQLiteConcurrencySettingsTests(SimpleTestCase):
    """Keep optional SQLite runtimes safe for concurrent process writers."""

    def test_sqlite_writers_wait_before_reading_claim_state(self):
        database = {"ENGINE": "django.db.backends.sqlite3", "OPTIONS": {}}
        configure_sqlite_concurrency(database, 2.0)

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "concurrency.sqlite3"
            self._create_job_table(path)
            first_writer_holds_lock = Event()
            release_first_writer = Event()
            second_writer_finished = Event()
            outcomes = []

            first = Thread(
                target=self._claim,
                args=(
                    path,
                    database["OPTIONS"],
                    "worker-a",
                    outcomes,
                    first_writer_holds_lock,
                    release_first_writer,
                    None,
                ),
            )
            second = Thread(
                target=self._claim,
                args=(
                    path,
                    database["OPTIONS"],
                    "worker-b",
                    outcomes,
                    None,
                    None,
                    second_writer_finished,
                ),
            )

            first.start()
            self.assertTrue(first_writer_holds_lock.wait(timeout=1))
            second.start()
            self.assertFalse(second_writer_finished.wait(timeout=0.1))
            release_first_writer.set()
            first.join(timeout=2)
            second.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertCountEqual(outcomes, [("worker-a", True), ("worker-b", False)])

    def test_non_sqlite_database_is_unchanged(self):
        database = {
            "ENGINE": "django.db.backends.postgresql",
            "OPTIONS": {"application_name": "awcenter"},
        }

        configure_sqlite_concurrency(database, 2.0)

        self.assertEqual(database["OPTIONS"], {"application_name": "awcenter"})

    def test_sqlite_timeout_must_be_positive(self):
        database = {"ENGINE": "django.db.backends.sqlite3"}

        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "SQLITE_BUSY_TIMEOUT_SECONDS must be greater than zero.",
        ):
            configure_sqlite_concurrency(database, 0)

    @staticmethod
    def _create_job_table(path):
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE job (id INTEGER PRIMARY KEY, status TEXT, worker_id TEXT)"
            )
            connection.execute(
                "INSERT INTO job (status, worker_id) VALUES ('queued', '')"
            )

    @staticmethod
    def _claim(
        path,
        options,
        worker_id,
        outcomes,
        lock_acquired,
        release_lock,
        finished,
    ):
        connection = sqlite3.connect(
            path,
            timeout=options["timeout"],
            isolation_level=None,
        )
        try:
            connection.execute(f"BEGIN {options['transaction_mode']}")
            row = connection.execute(
                "SELECT id FROM job WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            claimed = row is not None
            if claimed:
                connection.execute(
                    "UPDATE job SET status = 'running', worker_id = ? WHERE id = ?",
                    (worker_id, row[0]),
                )
            if lock_acquired:
                lock_acquired.set()
            if release_lock:
                release_lock.wait(timeout=1)
            connection.commit()
            outcomes.append((worker_id, claimed))
        finally:
            connection.close()
            if finished:
                finished.set()
