"""Credential decoding and integration defaults at the settings boundary."""
import base64
import os
import runpy
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

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

    def test_decoded_credentials_reach_integration_clients(self):
        from django.core.mail.backends.smtp import EmailBackend
        from integrations import docproof
        from integrations.doors.transport import DoorsOleTransport
        from integrations.doors.services import build_client_config as doors_config
        from integrations.teamcenter.services import build_client_config as teamcenter_config
        from integrations.teamcenter.auth import PasswordAuthenticator

        # A password that itself looks like Base64 must survive without a second decode.
        username, password = "örnek-user", encode("example-password")
        for use_overrides in (False, True):
            with self.subTest(use_overrides=use_overrides):
                environment = {
                    "AWCENTER_USERNAME": encode(username),
                    "AWCENTER_PASSWORD": encode(password),
                    "AWCENTER_MAIL_TRANSPORT": "django",
                    "DOCPROOF_URL": "https://docproof.example.test",
                    "TEAMCENTER_BASE_URL": "https://teamcenter.example.test",
                }
                if use_overrides:
                    environment.update(AWCENTER_USERNAME="", AWCENTER_PASSWORD="")
                    for prefix in ("DOCPROOF", "DOORS", "TEAMCENTER"):
                        environment[f"{prefix}_USERNAME"] = encode(username)
                        environment[f"{prefix}_PASSWORD"] = encode(password)
                    environment["EMAIL_HOST_USER"] = encode(username)
                    environment["EMAIL_HOST_PASSWORD"] = encode(password)
                values = self.load_settings(environment)
                integration_settings = {
                    key: value for key, value in values.items()
                    if key.startswith(("DOCPROOF_", "DOORS_", "TEAMCENTER_", "EMAIL_"))
                }
                with override_settings(**integration_settings):
                    client = Mock()
                    self.assertTrue(docproof.login(client))
                    self.assertEqual(client.post.call_args.kwargs["data"], {
                        "j_username": username, "j_password": password,
                    })
                    client.post.return_value.close.assert_called_once()
                    doors = doors_config()
                    self.assertEqual((doors.username, doors.password), (username, password))
                    with patch.object(DoorsOleTransport, "executable", Path("doors.exe")):
                        self.assertEqual(DoorsOleTransport(doors).start_command()[-4:],
                                         ["-u", username, "-P", password])
                    transport = Mock()
                    PasswordAuthenticator(teamcenter_config(), transport).login()
                    sent = transport.call.call_args.args[1]["credentials"]
                    self.assertEqual((sent["user"], sent["password"]), (username, password))
                    smtp = EmailBackend()
                    self.assertEqual((smtp.username, smtp.password), (username, password))

    def test_each_integration_rejects_invalid_encoded_credentials(self):
        names = ["EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"]
        names.extend(
            f"{prefix}_{suffix}"
            for prefix in ("DOCPROOF", "DOORS", "TEAMCENTER")
            for suffix in ("USERNAME", "PASSWORD")
        )
        for name in names:
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured) as caught:
                self.load_settings({name: "invalid-base64!"})
            self.assertEqual(str(caught.exception), f"{name} must contain a Base64-encoded UTF-8 value.")
