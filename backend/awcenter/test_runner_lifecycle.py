"""Protect source databases and restore settings when test setup fails."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .test_runner import ProcessSafeDiscoverRunner


class TestDatabaseLifecycleTests(SimpleTestCase):
    def test_setup_failure_restores_source_database_and_removes_temporary_files(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            source.write_bytes(b"source-must-not-change")
            configuration = {"NAME": str(source), "TEST": {"NAME": None}}
            connection = SimpleNamespace(vendor="sqlite", settings_dict=configuration)
            connections = MagicMock()
            connections.__getitem__.return_value = connection
            created = []

            def failing_setup(**_kwargs):
                temporary = Path(configuration["TEST"]["NAME"])
                temporary.write_bytes(b"partially-created-test-database")
                created.append(temporary)
                configuration["NAME"] = str(temporary)
                raise RuntimeError("Migration failed")

            with (
                patch.multiple(
                    "awcenter.test_runner",
                    connections=connections,
                    settings=SimpleNamespace(DATABASES={"default": configuration}),
                    create=True,
                ),
                patch("django.test.runner.DiscoverRunner.setup_databases", side_effect=failing_setup),
            ):
                runner = ProcessSafeDiscoverRunner(verbosity=0)
                with self.assertRaisesMessage(RuntimeError, "Migration failed"):
                    runner.setup_databases(aliases={"default"})

            self.assertEqual(configuration["NAME"], str(source))
            self.assertIsNone(configuration["TEST"]["NAME"])
            self.assertEqual(source.read_bytes(), b"source-must-not-change")
            self.assertFalse(created[0].parent.exists())

    def test_explicit_test_database_is_not_removed_by_custom_cleanup(self):
        with TemporaryDirectory() as directory:
            explicit = Path(directory) / "explicit.sqlite3"
            explicit.write_bytes(b"existing-test-database")
            configuration = {"NAME": "source.sqlite3", "TEST": {"NAME": str(explicit)}}
            connections = MagicMock()
            connections.__getitem__.return_value = SimpleNamespace(
                vendor="sqlite", settings_dict=configuration,
            )
            with (
                patch("awcenter.test_runner.connections", connections),
                patch("django.test.runner.DiscoverRunner.setup_databases", side_effect=RuntimeError("Failure")),
            ):
                runner = ProcessSafeDiscoverRunner(verbosity=0)
                with self.assertRaisesMessage(RuntimeError, "Failure"):
                    runner.setup_databases(aliases={"default"})
            self.assertEqual(configuration["TEST"]["NAME"], str(explicit))
            self.assertEqual(explicit.read_bytes(), b"existing-test-database")
