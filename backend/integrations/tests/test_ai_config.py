"""Single-provider configuration and safe readiness contracts."""

from django.test import SimpleTestCase, override_settings

from integrations.ai import config
from integrations.ai.contracts import AIServiceError


ABSENT_CONFIGURATION = {
    "AI_API_URL": None,
    "AI_API_MODEL_ID": None,
    "AI_API_TOKEN": None,
    "AI_API_ALLOWED_HOSTS": None,
    "AI_API_CONNECT_TIMEOUT_SECONDS": None,
    "AI_API_READ_TIMEOUT_SECONDS": None,
    "AI_API_MAX_RESPONSE_BYTES": None,
}
CENTRAL_CONFIGURATION = {
    "AI_API_URL": "https://central.example.test/chat/completions",
    "AI_API_MODEL_ID": "central-model",
    "AI_API_TOKEN": "synthetic-central-token",
    "AI_API_ALLOWED_HOSTS": "central.example.test",
}


@override_settings(**ABSENT_CONFIGURATION)
class AIConfigurationTests(SimpleTestCase):
    def test_central_configuration_preserves_provider_and_default_limits(self):
        with override_settings(**CENTRAL_CONFIGURATION):
            selected = config.resolve_configuration()
            self.assertEqual(config.configuration_status(), "configured")
        self.assertEqual(selected.url, "https://central.example.test/chat/completions")
        self.assertEqual(selected.model, "central-model")
        self.assertEqual(selected.token, "synthetic-central-token")
        self.assertEqual(selected.allowed_hosts, ("central.example.test",))
        self.assertEqual((selected.connect_timeout, selected.read_timeout), (5, 60))
        self.assertEqual(selected.max_response_bytes, 1048576)

    def test_removed_settings_cannot_activate_a_provider_or_fill_missing_fields(self):
        removed = {
            "ASSESSMENT_API_URL": "https://removed.example.test/chat",
            "ASSESSMENT_API_MODEL_ID": "removed-model",
            "ASSESSMENT_API_TOKEN": "synthetic-removed-token",
            "ASSESSMENT_API_ALLOWED_HOSTS": ["removed.example.test"],
        }
        with override_settings(**removed):
            self.assertEqual(config.configuration_status(), "unconfigured")
            with self.assertRaises(AIServiceError):
                config.resolve_configuration()
            with override_settings(AI_API_MODEL_ID="central-model"):
                self.assertEqual(config.configuration_status(), "invalid")
                with self.assertRaises(AIServiceError) as caught:
                    config.resolve_configuration()
                self.assertEqual(caught.exception.code, "AI_CONFIGURATION_ERROR")
                self.assertNotIn("synthetic", str(caught.exception))

    def test_explicit_empty_central_config_is_invalid(self):
        for name in CENTRAL_CONFIGURATION:
            with self.subTest(setting=name), override_settings(**{name: ""}):
                self.assertEqual(config.configuration_status(), "invalid")

    def test_absent_configuration_is_unconfigured(self):
        self.assertEqual(config.configuration_status(), "unconfigured")
        with self.assertRaises(AIServiceError):
            config.resolve_configuration()

    def test_invalid_and_empty_limits_are_rejected(self):
        for name, values in (
            ("AI_API_CONNECT_TIMEOUT_SECONDS", ("", "invalid", "nan", "0", "61")),
            ("AI_API_READ_TIMEOUT_SECONDS", ("", "301", "inf")),
            ("AI_API_MAX_RESPONSE_BYTES", ("", "1023", "10485761", "1.5")),
        ):
            for value in values:
                with self.subTest(setting=name, value=value), override_settings(
                    **CENTRAL_CONFIGURATION, **{name: value}
                ):
                    self.assertEqual(config.configuration_status(), "invalid")

    def test_central_limits_and_comma_separated_allowlist_are_resolved(self):
        with override_settings(
            **{**CENTRAL_CONFIGURATION, "AI_API_ALLOWED_HOSTS": "other.example.test, central.example.test"},
            AI_API_CONNECT_TIMEOUT_SECONDS="2.5",
            AI_API_READ_TIMEOUT_SECONDS="15",
            AI_API_MAX_RESPONSE_BYTES="2048",
        ):
            selected = config.resolve_configuration()
        self.assertEqual(selected.allowed_hosts, ("other.example.test", "central.example.test"))
        self.assertEqual((selected.connect_timeout, selected.read_timeout), (2.5, 15))
        self.assertEqual(selected.max_response_bytes, 2048)
