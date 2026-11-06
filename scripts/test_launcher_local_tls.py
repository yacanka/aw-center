"""Real HTTPS handshakes for the configured production server identity."""

import ipaddress
import json
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from scripts.launcher.installation_readiness import probe_http


class LocalTLSHandshakeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.received = []

    def identity(self, name, *, host='127.0.0.1', issuer=None, ca=False, expired=False):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, name)])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject)
                .issuer_name(issuer[0].subject if issuer else subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=2))
                .not_valid_after(now + timedelta(days=-1 if expired else 2))
                .add_extension(x509.BasicConstraints(ca=ca, path_length=None), True)
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]), False)
                .sign(issuer[1] if issuer else key, hashes.SHA256()))
        certificate, private_key = self.root / f'{name}.pem', self.root / f'{name}.key'
        certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        private_key.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        return cert, key, certificate, private_key

    def serve(self, identity, *, redirect=False):
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                self.send_response(302 if redirect else 200)
                if redirect:
                    self.send_header('Location', '/must-not-follow/')
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(identity[2]), str(identity[3]))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.shutdown)
        return f'https://127.0.0.1:{server.server_port}/health/ready/'

    def injected_probe(self, url, certificate):
        # The real native provider runs only in the client child, leaving the
        # server and other tests' SSL state untouched (including on Windows).
        program = '''import json, ssl, sys
from pip._vendor import truststore
truststore.inject_into_ssl()
provider = ssl.SSLContext
from scripts.launcher.installation_readiness import probe_http
details = []
ready = probe_http(sys.argv[1], sys.argv[2], diagnostic=details.append)
print(json.dumps({'ready': ready, 'provider_preserved': ssl.SSLContext is provider, 'details': details}))
'''
        result = subprocess.run([sys.executable, '-c', program, url, str(certificate)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['provider_preserved'])
        return report

    def test_non_ca_self_signed_server_with_native_trust_provider(self):
        identity = self.identity('local-server')
        context = ssl.create_default_context(cafile=str(identity[2]))
        self.assertEqual(context.get_ca_certs(), [], 'Fixture must reproduce the native CA export omission')
        self.assertTrue(self.injected_probe(self.serve(identity), identity[2])['ready'])
        self.assertEqual(self.received, ['/health/ready/'])

    def test_issued_server_leaf_is_sufficient_without_installing_its_root(self):
        issuer = self.identity('issuer', ca=True)
        identity = self.identity('issued-server', issuer=issuer)
        url = self.serve(identity)
        self.assertTrue(probe_http(url, str(identity[2])))
        self.assertTrue(self.injected_probe(url, identity[2])['ready'])

    def test_chain_bundle_pins_first_server_certificate(self):
        issuer = self.identity('issuer', ca=True)
        identity = self.identity('issued-server', issuer=issuer)
        identity[2].write_bytes(identity[2].read_bytes() + issuer[2].read_bytes())
        self.assertTrue(self.injected_probe(self.serve(identity), identity[2])['ready'])

    def test_wrong_ip_and_expired_certificate_fail_before_http(self):
        for label, options in (('wrong-ip', {'host': '127.0.0.2'}), ('expired', {'expired': True})):
            with self.subTest(label=label):
                identity = self.identity(label, **options)
                report = self.injected_probe(self.serve(identity), identity[2])
                self.assertFalse(report['ready'])
                self.assertIn('TLS sertifika doğrulaması', report['details'][0])
        self.assertEqual(self.received, [])

    def test_unselected_certificate_from_same_issuer_fails_before_http(self):
        issuer = self.identity('issuer', ca=True)
        selected = self.identity('selected', issuer=issuer)
        other = self.identity('other', issuer=issuer)
        selected[2].write_bytes(selected[2].read_bytes() + issuer[2].read_bytes())
        self.assertFalse(self.injected_probe(self.serve(other), selected[2])['ready'])
        self.assertEqual(self.received, [])

    def test_selected_ca_certificate_cannot_authorize_another_server(self):
        selected = self.identity('selected', ca=True)
        other = self.identity('other', issuer=selected)
        self.assertFalse(self.injected_probe(self.serve(other), selected[2])['ready'])
        self.assertEqual(self.received, [])

    def test_redirect_is_not_followed(self):
        identity = self.identity('local-server')
        report = self.injected_probe(self.serve(identity, redirect=True), identity[2])
        self.assertFalse(report['ready'])
        self.assertEqual(report['details'], ['HTTP 302'])
        self.assertEqual(self.received, ['/health/ready/'])

    def test_local_probe_does_not_use_ambient_proxy(self):
        identity = self.identity('local-server')
        with patch.dict('os.environ', {'HTTPS_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': '',
                                       'https_proxy': 'http://127.0.0.1:1', 'no_proxy': ''}):
            self.assertTrue(self.injected_probe(self.serve(identity), identity[2])['ready'])

    def test_probe_works_without_site_packages(self):
        identity = self.identity('local-server')
        program = ('import sys; from scripts.launcher.installation_readiness import probe_http; '
                   'sys.exit(0 if probe_http(sys.argv[1], sys.argv[2]) else 1)')
        result = subprocess.run([sys.executable, '-S', '-c', program, self.serve(identity), str(identity[2])],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
