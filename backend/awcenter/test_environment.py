import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import environ
from django.test import SimpleTestCase

from awcenter.settings import load_environment_files


class EnvironmentFilePrecedenceTests(SimpleTestCase):
    """Protect OS environment values from dotenv profile replacement."""

    def test_selected_profile_overrides_base_file_but_not_process_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            (base_dir / ".env").write_text(
                "AWCENTER_ENV_FILE=.env.production\n"
                "FROM_PROFILE=base\n"
                "PROCESS_VALUE=base\n",
                encoding="utf-8",
            )
            (base_dir / ".env.production").write_text(
                "FROM_PROFILE=production\n"
                "PROCESS_VALUE=profile\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PROCESS_VALUE": "process"}, clear=True):
                selected = load_environment_files(environ.Env(), base_dir)

                self.assertEqual(selected, base_dir / ".env.production")
                self.assertEqual(os.environ["FROM_PROFILE"], "production")
                self.assertEqual(os.environ["PROCESS_VALUE"], "process")

    def test_os_selected_profile_keeps_process_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            (base_dir / "custom.env").write_text(
                "PROCESS_VALUE=profile\nPROFILE_ONLY=value\n",
                encoding="utf-8",
            )
            process_environment = {
                "AWCENTER_ENV_FILE": "custom.env",
                "PROCESS_VALUE": "process",
            }
            with patch.dict(os.environ, process_environment, clear=True):
                selected = load_environment_files(environ.Env(), base_dir)

                self.assertEqual(selected, base_dir / "custom.env")
                self.assertEqual(os.environ["PROCESS_VALUE"], "process")
                self.assertEqual(os.environ["PROFILE_ONLY"], "value")
