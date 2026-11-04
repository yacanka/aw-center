"""Mandatory packaged dev/prod offline acceptance on a disposable Windows host."""
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from scripts import test_manager_package as fixtures
from scripts.manager_windows_acceptance import LiveAcceptance, deny_external_network


@unittest.skipUnless(os.name == 'nt' and os.environ.get('AWCENTER_RUN_MANAGER_WINDOWS_SMOKE') == '1',
                     'Requires the packaged native Windows acceptance job')
class NativeOfflineAcceptance(unittest.TestCase):
    environment = fixtures.NativeWindowsPackageTests.environment
    start_worker = fixtures.NativeWindowsPackageTests.start_worker
    stop_worker = staticmethod(fixtures.NativeWindowsPackageTests.stop_worker)
    next_event = fixtures.NativeWindowsPackageTests.next_event
    copy_clean_source = fixtures.NativeWindowsPackageTests.copy_clean_source
    provision_request = staticmethod(fixtures.NativeWindowsPackageTests.provision_request)

    @classmethod
    def setUpClass(cls):
        cls.executable = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        from scripts.manager.distribution import verify_distribution
        assert verify_distribution(cls.executable.parent).get('complete') is True
        cls.node = shutil.which('node')
        assert cls.node, 'The system-tools matrix requires a compatible system Node'
        cls.python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()

    def certificate(self, directory, host):
        # Only this disposable test helper gets cryptography; no global install.
        libraries = directory / 'test-libraries'
        result = subprocess.run([str(self.python), '-m', 'pip', '--isolated', 'install', '--no-index',
            '--find-links', str(self.executable.parent / 'dependencies/wheels'), '--target', str(libraries),
            'cryptography'], capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, 'Offline TLS test fixture dependencies are incomplete')
        script = '''import datetime, ipaddress, pathlib, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
directory, host = pathlib.Path(sys.argv[1]), sys.argv[2]
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'AWC acceptance')])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1))
        .not_valid_after(now+datetime.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True).sign(key, hashes.SHA256()))
(directory/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(directory/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
'''
        result = subprocess.run([str(self.python), '-c', script, str(directory), host],
            env={**os.environ, 'PYTHONPATH': str(libraries)}, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, 'TLS fixture creation failed')
        from scripts.launcher.installation_permissions import secure_path
        for name in ('cert.pem', 'key.pem'):
            secure_path(directory / name)

    def run_until_ready(self, directory, request, password):
        child, events = self.start_worker(self.executable, directory, request, network=True)
        deadline = time.monotonic() + 1200
        admin = False
        while True:
            event = self.next_event(child, events, deadline)
            self.assertNotIn(password, json.dumps(event))
            if event['type'] == 'input':
                admin = True
                child.stdin.write((json.dumps({'type': 'admin', 'value': {'username': 'U12345', 'password': password}}) + '\n').encode())
                child.stdin.flush()
            if event['type'] in {'error', 'done'}:
                self.fail('Native lifecycle failed: ' + json.dumps(event))
            if event['type'] == 'ready':
                return child, events, admin

    def stop_cleanly(self, child, events, host, ports):
        child.stdin.write(b'{"type":"cancel"}\n')
        child.stdin.flush()
        deadline = time.monotonic() + 90
        while True:
            event = self.next_event(child, events, deadline)
            if event['type'] == 'done':
                self.assertTrue(event['ok'])
                self.assertTrue(event['cancelled'])
                break
        child.wait(timeout=30)
        for port in ports:
            with socket.socket() as probe:
                probe.settimeout(1)
                self.assertNotEqual(probe.connect_ex((host, port)), 0)

    def test_dev_prod_system_and_managed_tools_with_real_network_denial(self):
        # Forced managed runs complement discovery's missing-tools unit tests.
        # A genuinely clean standard-user machine is also a release field gate.
        host = socket.gethostbyname(socket.gethostname())
        self.assertFalse(host.startswith('127.'), 'Production acceptance needs an assigned IPv4')
        for profile in ('dev', 'prod'):
            for system in (True, False):
                with self.subTest(profile=profile, system_tools=system), tempfile.TemporaryDirectory(prefix='awc-offline-') as temporary:
                    directory = Path(temporary).resolve()
                    source = self.copy_clean_source(self.executable, directory)
                    request = self.provision_request(source, 'offline')
                    request.update(profile=profile, offline_dir=str(self.executable.parent),
                                   install_python=not system, install_node=not system)
                    if system:
                        request.update(python_command=str(self.python), node_command=self.node)
                    if profile == 'prod':
                        self.certificate(directory, host)
                        request.update(host=host, tls_cert_file=str(directory / 'cert.pem'), tls_key_file=str(directory / 'key.pem'))
                    password = secrets.token_urlsafe(48)
                    with deny_external_network(host):
                        for address in ('1.1.1.1', '8.8.8.8'):
                            with self.assertRaises(OSError):
                                socket.create_connection((address, 443), timeout=2)
                        if profile == 'dev' and not system:
                            partial, partial_events = self.start_worker(self.executable, directory, request, network=True)
                            deadline = time.monotonic() + 300
                            while True:
                                event = self.next_event(partial, partial_events, deadline)
                                self.assertNotIn(event['type'], {'error', 'done'})
                                if event['type'] == 'phase' and event.get('message') == 'kilitli bağımlılıklar':
                                    break
                            partial.stdin.write(b'{"type":"cancel"}\n')
                            partial.stdin.flush()
                            while event['type'] != 'done':
                                event = self.next_event(partial, partial_events, deadline)
                            self.assertTrue(event.get('cancelled'))
                            partial.wait(timeout=30)
                            self.assertFalse((directory / 'local/AWCenter/config/dev.env').exists())
                        child, events, admin = self.run_until_ready(directory, request, password)
                        self.assertTrue(admin)
                        origin = f"https://{host}:{request['backend_port']}" if profile == 'prod' else f"http://127.0.0.1:{request['backend_port']}"
                        certificate = directory / 'cert.pem' if profile == 'prod' else None
                        job_id, digest = LiveAcceptance(origin, certificate).exercise(password)
                        private = directory / 'local/AWCenter'
                        saved = json.loads((private / 'config' / (profile + '.profile.json')).read_text(encoding='utf-8'))
                        self.assertEqual(bool(saved.get('python_executable')), system)
                        self.assertEqual(bool(saved.get('node_executable')), system)
                        duplicate, duplicate_events = self.start_worker(self.executable, directory,
                            {**request, 'action': 'start'}, network=True)
                        deadline = time.monotonic() + 30
                        while True:
                            event = self.next_event(duplicate, duplicate_events, deadline)
                            self.assertNotEqual(event['type'], 'ready')
                            if event['type'] == 'done':
                                self.assertFalse(event['ok'])
                                break
                        duplicate.wait(timeout=30)
                        actual_source = Path(saved['source_root'])
                        cli = subprocess.run([str(actual_source / '.venv/Scripts/python.exe'),
                            str(actual_source / 'launcher.py'), 'start', '--profile', profile],
                            cwd=actual_source, env=self.environment(directory, network=True),
                            capture_output=True, timeout=30)
                        self.assertNotEqual(cli.returncode, 0, 'CLI bypassed the live profile lease')
                        env = private / 'config' / (profile + '.env')
                        identity = hashlib.sha256(env.read_bytes()).hexdigest()
                        ports = [request['backend_port']] + ([request['frontend_port']] if profile == 'dev' else [])
                        bind = host if profile == 'prod' else '127.0.0.1'
                        self.stop_cleanly(child, events, bind, ports)
                        request['action'] = 'start'
                        if profile == 'prod' and not system:
                            child, events, admin = self.run_until_ready(directory, request, password)
                            self.stop_worker(child)  # Abrupt owner death must reap the entire tree.
                            child, events, admin = self.run_until_ready(directory, request, password)
                            self.assertFalse(admin)
                            self.assertEqual(hashlib.sha256(env.read_bytes()).hexdigest(), identity)
                            self.stop_cleanly(child, events, bind, ports)
                        request['action'] = 'start'
                        child, events, admin = self.run_until_ready(directory, request, password)
                        self.assertFalse(admin)
                        self.assertEqual(hashlib.sha256(env.read_bytes()).hexdigest(), identity)
                        live = LiveAcceptance(origin, certificate)
                        live.exercise(password)
                        with live.request('/api/jobs/' + job_id + '/download/') as response:
                            self.assertEqual(hashlib.sha256(response.read()).hexdigest(), digest)
                        self.stop_cleanly(child, events, bind, ports)
