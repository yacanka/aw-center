"""Custom CA bundles must be shared by live clients and anonymous probes."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, override_settings
from integrations.jira.client import JiraConnector, JiraConfigurationError, tls_verification
from integrations.probe_adapters import probe_jira, probe_teamcenter, probe_docproof, probe_numarator
from integrations.teamcenter.services import tls_verification as teamcenter_tls


class ImportedTlsTests(SimpleTestCase):
    def test_custom_bundles_are_used_by_all_probes(self):
        with TemporaryDirectory() as directory:
            certificate = Path(directory) / "ca.pem"
            certificate.touch()
            with override_settings(
                DEBUG=False, NUMARATOR_ENABLED=True, NUMARATOR_BASE_URL="https://num.example.invalid",
                NUMARATOR_CERTIFICATE_FILE=certificate, NUMARATOR_VERIFY_SSL=False, NUMARATOR_API_KEY="fixture",
                JIRA_ENABLED=True, TEAMCENTER_ENABLED=True, DOCPROOF_ENABLED=True,
                JIRA_URL="https://jira.example.invalid", TEAMCENTER_BASE_URL="https://tc.example.invalid",
                DOCPROOF_URL="https://doc.example.invalid", DOCPROOF_USERNAME="fixture", DOCPROOF_PASSWORD="fixture",
                JIRA_CERTIFICATE_FILE=certificate, TEAMCENTER_CERTIFICATE_FILE=certificate, DOCPROOF_CERTIFICATE_FILE=certificate,
            ), patch("integrations.probe_adapters.tls_head", return_value=Mock(status_code=200)) as head:
                for probe in (probe_jira, probe_teamcenter, probe_docproof, probe_numarator):
                    self.assertEqual(probe().status, "available")
                    self.assertEqual(head.call_args.kwargs["verify"], str(certificate))
                self.assertEqual(tls_verification(), str(certificate))
                self.assertEqual(teamcenter_tls(), str(certificate))
                from integrations.numarator.client import NumaratorClient
                from awcenter.checks import production_runtime_checks
                client = NumaratorClient()
                self.addCleanup(client.session.close)
                self.assertEqual(client.session.verify, str(certificate))
                self.assertNotIn("awcenter.E029", {error.id for error in production_runtime_checks(None)})
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

    @override_settings(NUMARATOR_ENABLED=True, NUMARATOR_API_KEY="fixture",
                       NUMARATOR_BASE_URL="https://num.example.invalid",
                       NUMARATOR_CERTIFICATE_FILE=Path("/missing-ca.pem"))
    def test_numarator_missing_bundle_keeps_boolean_verification(self):
        from integrations.numarator.client import NumaratorClient

        for verify in (True, False):
            with self.subTest(verify=verify), override_settings(NUMARATOR_VERIFY_SSL=verify):
                client = NumaratorClient()
                self.addCleanup(client.session.close)
                self.assertIs(client.session.verify, verify)


class DocProofExplicitCaTests(SimpleTestCase):
    @override_settings(DOCPROOF_CERTIFICATE_FILE=None, DOCPROOF_VERIFY_SSL=True)
    def test_no_custom_ca_uses_system_trust(self):
        from integrations.docproof import tls_verification
        self.assertIs(tls_verification(), True)

    @override_settings(DOCPROOF_CERTIFICATE_FILE=Path('/missing-explicit-ca.pem'))
    def test_missing_explicit_ca_fails_before_authentication(self):
        from integrations.docproof import search_document_issue
        from requests.exceptions import RequestException
        with override_settings(DOCPROOF_ENABLED=True), patch('integrations.docproof.login') as login, patch(
            'requests.Session.send', side_effect=RequestException('Synthetic upstream failure')
        ):
            with self.assertRaises(RequestException) as raised:
                search_document_issue('SYNTHETIC-1')
            self.assertNotIn('missing-explicit-ca', str(raised.exception))
        login.assert_not_called()

    @override_settings(DOCPROOF_ENABLED=True, DOCPROOF_URL="https://doc.example.invalid",
                       DOCPROOF_USERNAME="fixture", DOCPROOF_PASSWORD="fixture",
                       DOCPROOF_CERTIFICATE_FILE=Path("/missing-explicit-ca.pem"))
    def test_invalid_ca_probe_is_sanitized_without_network(self):
        with patch("integrations.probe_adapters.tls_head") as head:
            outcome = probe_docproof()
        self.assertEqual(outcome.status, "degraded")
        self.assertNotIn("missing-explicit-ca", outcome.detail)
        head.assert_not_called()

    def test_explicit_ca_wins_over_ambient_ca_for_login_and_search(self):
        import os
        import requests
        from integrations.docproof import search_document_issue
        with TemporaryDirectory() as directory:
            certificate = Path(directory) / 'approved.pem'
            certificate.touch()
            observed = []
            def send(session, request, **kwargs):
                observed.append(kwargs['verify'])
                response = requests.Response()
                response.status_code = 200
                response._content = b'{"total": 0, "entries": []}'
                response._content_consumed = True
                return response
            with override_settings(DOCPROOF_ENABLED=True, DOCPROOF_URL='https://doc.example.invalid',
                                   DOCPROOF_USERNAME='fixture', DOCPROOF_PASSWORD='fixture',
                                   DOCPROOF_CERTIFICATE_FILE=certificate), patch.dict(
                os.environ, {'REQUESTS_CA_BUNDLE': '/synthetic/ambient.pem',
                             'CURL_CA_BUNDLE': '/synthetic/other.pem'}
            ), patch.object(requests.Session, 'send', send):
                self.assertEqual(search_document_issue('EXAMPLE-1'), (None, 'missing'))
            self.assertEqual(observed, [str(certificate), str(certificate)])
