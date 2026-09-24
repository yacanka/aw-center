"""Credential decoding and integration defaults at the settings boundary."""
import base64
import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from awcenter.settings import credential_from_env


def encode(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


class CredentialSettingsTests(SimpleTestCase):
    def load_settings(self, values):
        environment = {
            "AWCENTER_ENV_FILE": os.devnull,
            "DEBUG": "True",
            "AWCENTER_USERNAME": encode("örnek-user"),
            "AWCENTER_PASSWORD": encode("example-password"),
            **values,
        }
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(Path(__file__).with_name("settings.py")))

    def test_all_integrations_inherit_decoded_defaults(self):
        values = self.load_settings({"AWCENTER_MAIL_TRANSPORT": "django"})
        for name in ("USERNAME", "DOCPROOF_USERNAME", "DOORS_USERNAME", "TEAMCENTER_USERNAME", "EMAIL_HOST_USER"):
            self.assertEqual(values[name], "örnek-user")
        for name in ("PASSWORD", "DOCPROOF_PASSWORD", "DOORS_PASSWORD", "TEAMCENTER_PASSWORD", "EMAIL_HOST_PASSWORD"):
            self.assertEqual(values[name], "example-password")

    def test_explicit_overrides_and_empty_fallbacks(self):
        for prefix in ("DOCPROOF", "DOORS", "TEAMCENTER"):
            with self.subTest(prefix=prefix):
                values = self.load_settings({
                    f"{prefix}_USERNAME": encode("override"),
                    f"{prefix}_PASSWORD": "",
                })
                self.assertEqual(values[f"{prefix}_USERNAME"], "override")
                self.assertEqual(values[f"{prefix}_PASSWORD"], "example-password")

    def test_mail_overrides_are_decoded(self):
        values = self.load_settings({
            "AWCENTER_MAIL_TRANSPORT": "django",
            "EMAIL_HOST_USER": encode("smtp-user"),
            "EMAIL_HOST_PASSWORD": encode("smtp-password"),
        })
        self.assertEqual(values["EMAIL_HOST_USER"], "smtp-user")
        self.assertEqual(values["EMAIL_HOST_PASSWORD"], "smtp-password")

    def test_disabled_mail_does_not_inherit_shared_credentials(self):
        values = self.load_settings({"AWCENTER_MAIL_TRANSPORT": "disabled"})
        self.assertEqual(values["EMAIL_HOST_USER"], "")
        self.assertEqual(values["EMAIL_HOST_PASSWORD"], "")

    def test_missing_shared_credentials_ignore_windows_username(self):
        values = self.load_settings({"AWCENTER_USERNAME": "", "AWCENTER_PASSWORD": "", "USERNAME": "windows-user"})
        self.assertEqual(values["USERNAME"], "")
        self.assertEqual(values["PASSWORD"], "")
        self.assertEqual(values["DOORS_USERNAME"], "")

    def test_invalid_values_fail_without_exposing_value_or_cause(self):
        for value in ("not-base64!", "YQ", "/w==", "şifre", "Y Q=="):
            with self.subTest(value=value), patch.dict(os.environ, {"AWCENTER_PASSWORD": value}):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    credential_from_env("AWCENTER_PASSWORD")
                self.assertEqual(str(caught.exception), "AWCENTER_PASSWORD must contain a Base64-encoded UTF-8 value.")
                self.assertTrue(caught.exception.__suppress_context__)

    def test_decoding_preserves_whitespace_and_does_not_decode_twice(self):
        with patch.dict(os.environ, {"AWCENTER_PASSWORD": encode(" cGFzcw== \n")}):
            self.assertEqual(credential_from_env("AWCENTER_PASSWORD"), " cGFzcw== \n")
