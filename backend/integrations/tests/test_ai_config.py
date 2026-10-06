"""Provider-family selection and safe configuration readiness contracts."""

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
    "ASSESSMENT_API_URL": "",
    "ASSESSMENT_API_MODEL_ID": "",
    "ASSESSMENT_API_TOKEN": "",
    "ASSESSMENT_API_ALLOWED_HOSTS": [],
    "ASSESSMENT_API_CONNECT_TIMEOUT_SECONDS": 5.0,
    "ASSESSMENT_API_READ_TIMEOUT_SECONDS": 60.0,
    "ASSESSMENT_API_MAX_RESPONSE_BYTES": 1048576,
}
CENTRAL_CONFIGURATION = {
    "AI_API_URL": "https://central.example.test/chat/completions",
    "AI_API_MODEL_ID": "central-model",
    "AI_API_TOKEN": "synthetic-central-token",
    "AI_API_ALLOWED_HOSTS": "central.example.test",
}
LEGACY_CONFIGURATION = {
    "ASSESSMENT_API_URL": "https://legacy.example.test/chat/completions",
    "ASSESSMENT_API_MODEL_ID": "legacy-model",
    "ASSESSMENT_API_TOKEN": "synthetic-legacy-token",
    "ASSESSMENT_API_ALLOWED_HOSTS": ["legacy.example.test"],
    "ASSESSMENT_API_CONNECT_TIMEOUT_SECONDS": 3.0,
    "ASSESSMENT_API_READ_TIMEOUT_SECONDS": 20.0,
    "ASSESSMENT_API_MAX_RESPONSE_BYTES": 4096,
}


@override_settings(**ABSENT_CONFIGURATION)
class AIConfigurationTests(SimpleTestCase):
    def test_central_absence_uses_whole_legacy_family(self):
        with override_settings(**LEGACY_CONFIGURATION):
            selected = config.resolve_configuration()
        self.assertEqual(selected.url, "https://legacy.example.test/chat/completions")
        self.assertEqual(selected.model, "legacy-model")
        self.assertEqual(selected.token, "synthetic-legacy-token")
        self.assertEqual(selected.allowed_hosts, ("legacy.example.test",))
        self.assertEqual((selected.connect_timeout, selected.read_timeout), (3, 20))
        self.assertEqual(selected.max_response_bytes, 4096)

    def test_partial_central_config_does_not_borrow_legacy_fields(self):
        with override_settings(**LEGACY_CONFIGURATION, AI_API_MODEL_ID="central-model"):
            with self.assertRaises(AIServiceError) as caught:
                config.resolve_configuration()
            self.assertEqual(config.configuration_status(), "invalid")
        self.assertEqual(caught.exception.code, "AI_CONFIGURATION_ERROR")
        self.assertNotIn("synthetic", str(caught.exception))

    def test_explicit_empty_central_config_is_invalid(self):
        for name in CENTRAL_CONFIGURATION:
            with self.subTest(setting=name), override_settings(**{name: ""}):
                self.assertEqual(config.configuration_status(), "invalid")

    def test_assessment_prefers_explicit_legacy_family(self):
        with override_settings(**CENTRAL_CONFIGURATION, **LEGACY_CONFIGURATION):
            self.assertEqual(config.resolve_configuration().model, "central-model")
            self.assertEqual(config.resolve_configuration(prefer_assessment=True).model, "legacy-model")

    def test_assessment_uses_central_when_legacy_absent(self):
        with override_settings(**CENTRAL_CONFIGURATION):
            selected = config.resolve_configuration(prefer_assessment=True)
        self.assertEqual(selected.model, "central-model")
        self.assertEqual((selected.connect_timeout, selected.read_timeout), (5, 60))
        self.assertEqual(selected.max_response_bytes, 1048576)

    def test_absent_families_are_unconfigured(self):
        self.assertEqual(config.configuration_status(), "unconfigured")
        with self.assertRaises(AIServiceError):
            config.resolve_configuration()

    def test_partial_legacy_never_borrows_central_fields(self):
        with override_settings(**CENTRAL_CONFIGURATION, ASSESSMENT_API_TOKEN="synthetic-token"):
            self.assertEqual(config.configuration_status(), "configured")
            self.assertEqual(config.configuration_status(prefer_assessment=True), "invalid")
            with self.assertRaises(AIServiceError):
                config.resolve_configuration(prefer_assessment=True)

    def test_invalid_and_empty_limits_are_rejected_without_fallback(self):
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
