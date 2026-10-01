"""Disposable SQLite databases shared with spawned executor test processes."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.db import connections
from django.test.runner import DiscoverRunner


class ProcessSafeDiscoverRunner(DiscoverRunner):
    """Use disk-backed SQLite tests; preserve explicit databases and other engines.

    In-memory SQLite cannot be shared with a fresh ``spawn`` interpreter.
    Only the automatically selected test database changes, never the configured
    development/production database. Explicit TEST.NAME retains Django's normal
    lifecycle, including --keepdb. Automatically allocated files are disposable.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.parallel > 1 and connections["default"].vendor == "sqlite":
            # Django's spawn pool converts SQLite clones to memory, and daemon
            # pool workers cannot start the real executor subprocesses tested here.
            self.parallel = 1
            self.log(
                "SQLite tests run serially to support real executor subprocesses; "
                "--parallel is ignored for SQLite.",
                level=logging.WARNING,
            )

    def setup_databases(self, **kwargs):
        self._sqlite_directory = None
        self._sqlite_test_settings = None
        default = connections["default"]
        aliases = kwargs.get("aliases")
        uses_default = aliases is None or "default" in aliases
        test_settings = default.settings_dict["TEST"]
        test_name = test_settings.get("NAME")
        if uses_default and default.vendor == "sqlite" and not test_name:
            self._sqlite_directory = TemporaryDirectory(prefix="awcenter-test-")
            self._sqlite_test_settings = test_settings
            self._sqlite_original_name = test_name
            self._sqlite_source_name = default.settings_dict["NAME"]
            test_settings["NAME"] = str(Path(self._sqlite_directory.name) / "test.sqlite3")
        try:
            return super().setup_databases(**kwargs)
        except BaseException:
            self._cleanup_sqlite_database()
            raise

    def teardown_databases(self, old_config, **kwargs):
        try:
            super().teardown_databases(old_config, **kwargs)
        finally:
            self._cleanup_sqlite_database()

    def _cleanup_sqlite_database(self):
        if self._sqlite_directory is None:
            return
        connections.close_all()
        connections["default"].settings_dict["NAME"] = self._sqlite_source_name
        settings.DATABASES["default"]["NAME"] = self._sqlite_source_name
        self._sqlite_test_settings["NAME"] = self._sqlite_original_name
        self._sqlite_directory.cleanup()
        self._sqlite_directory = None
