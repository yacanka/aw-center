"""Load mail configuration in an isolated settings process."""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase


class MailTimeoutSettingsTests(SimpleTestCase):
    def load_settings(self, timeout, *, lease="900"):
        with TemporaryDirectory() as directory:
            environment_file = Path(directory) / "empty.env"
            environment_file.touch()
            environment = os.environ.copy()
            environment.update(
                DEBUG="True",
                AWCENTER_DEPLOYMENT_MODE="development",
                AWCENTER_ENV_FILE=str(environment_file),
                EMAIL_TIMEOUT=timeout,
                COMPDOC_NOTIFICATION_LOCK_SECONDS=lease,
            )
            return subprocess.run(
                [sys.executable, "-c", "import awcenter.settings"],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_rejects_unbounded_and_non_positive_smtp_timeouts(self):
        for value in ("0", "-1", "30.1", "nan", "inf"):
            with self.subTest(timeout=value):
                result = self.load_settings(value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("EMAIL_TIMEOUT", result.stderr)

    def test_accepts_bounded_smtp_timeouts(self):
        for value in ("0.5", "10", "30"):
            with self.subTest(timeout=value):
                self.assertEqual(self.load_settings(value).returncode, 0)

    def test_timeout_cannot_reach_effective_notification_lease(self):
        result = self.load_settings("30", lease="30")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shorter than the notification lease", result.stderr)
