"""Tests for safe, cached, circuit-broken integration health probes."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
import requests

from awcenter.integration_probe_adapters import ProbeOutcome, probe_jira
from awcenter.integration_probes import _get_probe, claim_refresh_slot, probe_catalog


class IntegrationProbeAdapterTests(SimpleTestCase):
    """Verify external probes are bounded, anonymous, and sanitized."""

    @override_settings(
        DEBUG=False,
        JIRA_BTB_URL="https://jira.internal.example",
        INTEGRATION_PROBE_CONNECT_TIMEOUT_SECONDS=1.5,
        INTEGRATION_PROBE_READ_TIMEOUT_SECONDS=2.5,
    )
    @patch("awcenter.integration_probe_adapters.requests.head")
    def test_http_probe_sends_no_credentials(self, get_mock):
        """Reachability checks never forward application credentials or cookies."""

        get_mock.return_value = MagicMock(status_code=401)

        outcome = probe_jira()

        self.assertEqual(outcome.status, "available")
        _, keyword_arguments = get_mock.call_args
        self.assertNotIn("auth", keyword_arguments)
        self.assertNotIn("cookies", keyword_arguments)
        self.assertEqual(keyword_arguments["timeout"], (1.5, 2.5))
        self.assertTrue(keyword_arguments["verify"])
        self.assertFalse(keyword_arguments["allow_redirects"])

    @override_settings(DEBUG=False, JIRA_BTB_URL="http://jira.internal.example")
    @patch("awcenter.integration_probe_adapters.requests.head")
    def test_insecure_production_transport_is_not_called(self, get_mock):
        """Production probes fail closed before contacting an insecure origin."""

        outcome = probe_jira()

        self.assertEqual(outcome.status, "degraded")
        get_mock.assert_not_called()

    @override_settings(DEBUG=True, JIRA_BTB_URL="http://localhost:8080")
    @patch("awcenter.integration_probe_adapters.requests.head")
    def test_network_exception_returns_sanitized_result(self, get_mock):
        """Connection exceptions never expose hostnames or library diagnostics."""

        get_mock.side_effect = requests.ConnectionError("secret internal diagnostic")

        outcome = probe_jira()

        self.assertEqual(outcome.status, "unavailable")
        self.assertNotIn("secret", outcome.detail)
        self.assertNotIn("localhost", outcome.detail)

    @override_settings(DEBUG=False, JIRA_BTB_URL="https://user:password@jira.example")
    @patch("awcenter.integration_probe_adapters.requests.head")
    def test_url_embedded_credentials_are_rejected(self, head_mock):
        """Probe URLs cannot smuggle Basic credentials into the HTTP client."""

        outcome = probe_jira()

        self.assertEqual(outcome.status, "degraded")
        head_mock.assert_not_called()


@override_settings(
    INTEGRATION_PROBE_CACHE_SECONDS=30,
    INTEGRATION_PROBE_MAX_WORKERS=2,
    INTEGRATION_PROBE_FAILURE_THRESHOLD=3,
    INTEGRATION_PROBE_FAILURE_WINDOW_SECONDS=300,
    INTEGRATION_PROBE_CIRCUIT_COOLDOWN_SECONDS=120,
    INTEGRATION_PROBE_READ_TIMEOUT_SECONDS=3,
)
class IntegrationProbeOrchestrationTests(SimpleTestCase):
    """Verify caching, failure isolation, and circuit breaker state."""

    def setUp(self):
        """Start every orchestration test with an empty cache."""

        cache.clear()

    @patch("awcenter.integration_probes.probe_integration")
    def test_cached_result_avoids_duplicate_probe(self, probe_mock):
        """Repeated catalog reads reuse the bounded-TTL observation."""

        probe_mock.return_value = ProbeOutcome("available", "Service is reachable.")
        catalog = [{"id": "jira"}]

        first = probe_catalog(catalog)
        second = probe_catalog(catalog)

        self.assertEqual(first[0]["health"]["source"], "live")
        self.assertEqual(second[0]["health"]["source"], "cache")
        probe_mock.assert_called_once_with("jira")

    @patch("awcenter.integration_probes.probe_integration")
    def test_repeated_failures_open_circuit(self, probe_mock):
        """Three failed refreshes pause further calls during cooldown."""

        probe_mock.return_value = ProbeOutcome("unavailable", "Service is unreachable.")

        for _ in range(3):
            _get_probe("jira", refresh=True)
        circuit_result = _get_probe("jira", refresh=True)

        self.assertEqual(circuit_result["source"], "circuit")
        self.assertEqual(circuit_result["status"], "unavailable")
        self.assertEqual(probe_mock.call_count, 3)

    @patch("awcenter.integration_probes.probe_integration")
    def test_adapter_exception_is_sanitized_and_cached(self, probe_mock):
        """Unexpected adapter failures become safe health observations."""

        probe_mock.side_effect = RuntimeError("credential=value")

        result = _get_probe("jira", refresh=True)

        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("credential", result["detail"])
        self.assertEqual(result["source"], "live")

    @override_settings(INTEGRATION_PROBE_REFRESH_COOLDOWN_SECONDS=10)
    def test_forced_refresh_is_rate_limited_per_user(self):
        """Repeated refresh clicks cannot bypass caching continuously."""

        self.assertTrue(claim_refresh_slot("user-1"))
        self.assertFalse(claim_refresh_slot("user-1"))
        self.assertTrue(claim_refresh_slot("user-2"))
