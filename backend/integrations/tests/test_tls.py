"""Exercise integration trust against ephemeral TLS servers and CA chains."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import ssl
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from django.test import SimpleTestCase
import requests


def certificate(key, name, *, issuer=None, ca=False, san=True):
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    builder = (x509.CertificateBuilder().subject_name(subject)
               .issuer_name(issuer[1].subject if issuer else subject)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
               .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False,
                              content_commitment=False, data_encipherment=False, key_agreement=False,
                              key_cert_sign=ca, crl_sign=ca, encipher_only=False, decipher_only=False), critical=True))
    if not ca and san:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
    return builder.sign(issuer[0] if issuer else key, hashes.SHA256())


class IntegrationTlsTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temporary = TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.authorities = []
        for name in ('system', 'custom', 'untrusted'):
            key = ec.generate_private_key(ec.SECP256R1())
            cert = certificate(key, name, ca=True)
            path = cls.root / f'{name}.pem'
            path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            cls.authorities.append((key, cert, path))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        super().tearDownClass()

    def system_context(self):
        # Model native Windows ROOT/CA loading without changing the host store.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(self.authorities[0][2]))
        return context

    def server_context(self, authority, *, san=True):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = certificate(key, 'localhost', issuer=authority, san=san)
        certificate_file = self.root / 'server.pem'
        key_file = self.root / 'server-key.pem'
        certificate_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                             serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate_file, key_file)
        return context

    def handshake(self, session, authority, hostname='localhost'):
        """Run a real TLS exchange in memory, without requiring listener access."""
        request = requests.Request('GET', f'https://{hostname}').prepare()
        verification = session.merge_environment_settings(request.url, {}, None, None, None)['verify']
        adapter = session.get_adapter(request.url)
        _, pool = adapter.build_connection_pool_key_attributes(request, verification)
        context = pool['ssl_context']
        self.handshake_context(context, authority, hostname)

    def handshake_context(self, context, authority, hostname='localhost', *, san=True):
        client_input, client_output = ssl.MemoryBIO(), ssl.MemoryBIO()
        server_input, server_output = ssl.MemoryBIO(), ssl.MemoryBIO()
        client = context.wrap_bio(client_input, client_output, server_hostname=hostname)
        server = self.server_context(authority, san=san).wrap_bio(server_input, server_output, server_side=True)
        complete = set()
        for _ in range(10):
            for peer in (client, server):
                try:
                    peer.do_handshake()
                    complete.add(peer)
                except ssl.SSLWantReadError:
                    pass
            server_input.write(client_output.read())
            client_input.write(server_output.read())
            if len(complete) == 2:
                return
        self.fail('TLS exchange did not complete')

    def session(self, verification=True):
        from integrations.tls import configure_session_tls
        session = requests.Session()
        session.trust_env = False
        configure_session_tls(session, verification)
        self.addCleanup(session.close)
        return session

    def test_custom_ca_supplements_system_and_public_trust(self):
        session = self.session(str(self.authorities[1][2]))
        with patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            for authority in self.authorities[:2]:
                with self.subTest(authority=authority[1].subject):
                    self.handshake(session, authority)
        adapter = session.get_adapter('https://')
        prepared = requests.Request('GET', 'https://localhost').prepare()
        _, pool = adapter.build_connection_pool_key_attributes(prepared, True)
        self.assertGreater(len(pool['ssl_context'].get_ca_certs()), 2)
        self.assertTrue(pool['ssl_context'].check_hostname)
        self.assertEqual(pool['ssl_context'].verify_mode, ssl.CERT_REQUIRED)

    def test_without_custom_ca_trusts_system_authority(self):
        with patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            self.handshake(self.session(), self.authorities[0])

    def test_untrusted_authority_and_hostname_mismatch_remain_rejected(self):
        with patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            session = self.session(str(self.authorities[1][2]))
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.handshake(session, self.authorities[2])
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.handshake(session, self.authorities[1], hostname='127.0.0.1')

    def test_explicit_custom_ca_wins_over_ambient_bundle(self):
        session = self.session(str(self.authorities[1][2]))
        session.trust_env = True
        with patch.dict(os.environ, {'REQUESTS_CA_BUNDLE': str(self.root / 'ambient-missing.pem'),
                                     'NO_PROXY': '*'}), \
             patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            self.handshake(session, self.authorities[1])

    def test_ambient_bundle_adds_trust_when_no_custom_ca_selected(self):
        session = self.session()
        session.trust_env = True
        with patch.dict(os.environ, {'REQUESTS_CA_BUNDLE': str(self.authorities[1][2]), 'NO_PROXY': '*'}), \
             patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            for authority in self.authorities[:2]:
                self.handshake(session, authority)

    def test_invalid_custom_ca_has_safe_error_before_network(self):
        invalid = self.root / 'invalid.pem'
        invalid.write_text('invalid', encoding='ascii')
        session = self.session(str(invalid))
        with patch('urllib3.connection.HTTPSConnection.connect') as connect:
            with self.assertRaises(requests.exceptions.SSLError) as raised:
                session.get('https://localhost', timeout=2)
        self.assertNotIn(str(invalid), str(raised.exception))
        connect.assert_not_called()

    def test_contexts_are_reused_and_bounded_per_session(self):
        adapter = self.session().get_adapter('https://')
        prepared = requests.Request('GET', 'https://localhost').prepare()
        first = adapter.build_connection_pool_key_attributes(prepared, True)[1]['ssl_context']
        second = adapter.build_connection_pool_key_attributes(prepared, True)[1]['ssl_context']
        self.assertIs(first, second)
        for authority in self.authorities:
            adapter.build_connection_pool_key_attributes(prepared, str(authority[2]))
        self.assertLessEqual(len(adapter._contexts), 2)

    def test_custom_ca_does_not_contaminate_other_sessions(self):
        with patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            self.handshake(self.session(str(self.authorities[1][2])), self.authorities[1])
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.handshake(self.session(), self.authorities[1])

    def test_https_proxy_uses_same_additive_trust_as_destination(self):
        session = self.session(str(self.authorities[1][2]))
        request = requests.Request('GET', 'https://destination.invalid').prepare()
        adapter = session.get_adapter(request.url)
        with patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            connection = adapter.get_connection_with_tls_context(
                request, True, proxies={'https': 'https://proxy.invalid:8443'})
            context = connection.proxy_config.ssl_context
            self.assertIsNot(context, connection.conn_kw['ssl_context'])
            for authority in self.authorities[:2]:
                self.handshake_context(context, authority)
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.handshake_context(context, self.authorities[2])

    def test_debug_explicit_disabled_verification_is_preserved(self):
        adapter = self.session(False).get_adapter('https://')
        request = requests.Request('GET', 'https://localhost').prepare()
        _, pool = adapter.build_connection_pool_key_attributes(request, True)
        self.assertNotIn('ssl_context', pool)
        self.assertEqual(pool['cert_reqs'], 'CERT_NONE')

    def test_legacy_common_name_without_san_is_rejected(self):
        adapter = self.session().get_adapter('https://')
        request = requests.Request('GET', 'https://localhost').prepare()
        with patch('integrations.tls.ssl.create_default_context', side_effect=self.system_context):
            _, pool = adapter.build_connection_pool_key_attributes(request, True)
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.handshake_context(pool['ssl_context'], self.authorities[0], san=False)

    def test_client_certificate_identities_have_isolated_contexts(self):
        adapter = self.session().get_adapter('https://')
        request = requests.Request('GET', 'https://localhost').prepare()
        contexts = []
        for identity in (None, ('client-a.pem', 'client-a.key'), ('client-b.pem', 'client-b.key')):
            _, pool = adapter.build_connection_pool_key_attributes(request, True, identity)
            contexts.append(pool['ssl_context'])
            if identity is not None:
                self.assertEqual(pool['cert_file'], identity[0])
                self.assertEqual(pool['key_file'], identity[1])
        self.assertEqual(len({id(context) for context in contexts}), 3)
