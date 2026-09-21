"""Custom CA bundles must be shared by live clients and anonymous probes."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, override_settings
from integrations.jira.client import JiraConnector, JiraConfigurationError, tls_verification
from integrations.probe_adapters import probe_jira, probe_teamcenter, probe_docproof
from integrations.teamcenter.services import tls_verification as teamcenter_tls


class ImportedTlsTests(SimpleTestCase):
    def test_custom_bundles_are_used_by_all_probes(self):
        with TemporaryDirectory() as directory:
            certificate = Path(directory) / "ca.pem"
            certificate.touch()
            with override_settings(
                DEBUG=False, JIRA_ENABLED=True, TEAMCENTER_ENABLED=True, DOCPROOF_ENABLED=True,
                JIRA_URL="https://jira.example.invalid", TEAMCENTER_BASE_URL="https://tc.example.invalid",
                DOCPROOF_URL="https://doc.example.invalid", DOCPROOF_USERNAME="fixture", DOCPROOF_PASSWORD="fixture",
                JIRA_CERTIFICATE_FILE=certificate, TEAMCENTER_CERTIFICATE_FILE=certificate, DOCPROOF_CERTIFICATE_FILE=certificate,
            ), patch("integrations.probe_adapters.requests.head", return_value=Mock(status_code=200)) as head:
                for probe in (probe_jira, probe_teamcenter, probe_docproof):
                    self.assertEqual(probe().status, "available")
                    self.assertEqual(head.call_args.kwargs["verify"], str(certificate))
                self.assertEqual(tls_verification(), str(certificate))
                self.assertEqual(teamcenter_tls(), str(certificate))
                with patch("integrations.jira.client.JIRA") as jira:
                    JiraConnector("https://jira.example.invalid", "fixture-session")
                    self.assertEqual(jira.call_args.kwargs["options"]["verify"], str(certificate))

    @override_settings(DEBUG=False, JIRA_VERIFY_SSL=False, JIRA_CERTIFICATE_FILE=Path("/missing-ca.pem"))
    def test_insecure_production_jira_fails_before_sending_credentials(self):
        with patch("integrations.jira.client.JIRA") as jira, self.assertRaises(JiraConfigurationError):
            JiraConnector("https://jira.example.invalid", "fixture-session")
        jira.assert_not_called()

    @override_settings(JIRA_VERIFY_SSL=True, JIRA_CERTIFICATE_FILE=Path("/missing-ca.pem"))
    def test_missing_bundle_keeps_system_verification(self):
        self.assertIs(tls_verification(), True)
