"""Package trust unions retain native/tool roots without distributable PEM state."""

from pathlib import Path
import json
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from scripts.launcher import certificates
from scripts.launcher.model import LauncherError


class PackageTrustTests(unittest.TestCase):
    def test_target_python_with_real_startup_truststore_hook_can_export_pip_roots(self):
        venv = self.root / 'python-tools'
        subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True,
                       capture_output=True, timeout=60)
        python = venv / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        location = subprocess.run([str(python), '-c',
            'import json,sysconfig; print(json.dumps(sysconfig.get_path("purelib")))'],
            capture_output=True, text=True, check=True, timeout=10)
        site = Path(json.loads(location.stdout))
        (site / 'truststore-fixture.pth').write_text(
            'import pip._vendor.truststore as truststore; truststore.inject_into_ssl()\n', encoding='ascii')
        probe = subprocess.run([str(python), '-I', '-B', '-c',
                                'import ssl; print(ssl.SSLContext.__module__)'],
                               capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(probe.stdout.strip(), 'pip._vendor.truststore._api')
        exported = certificates._python_roots(python, {})
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=exported)
        self.assertGreater(len(context.get_ca_certs()), 0)

    def test_managed_trust_export_with_real_injected_truststore_keeps_provider_and_roots(self):
        program = '''import json, os, ssl, sys, threading
from pathlib import Path
from pip._vendor import truststore
from scripts.launcher import certificates
from scripts.launcher.process import operation_control
expected = set(ssl.create_default_context().get_ca_certs(binary_form=True))
python = sys.executable
truststore.inject_into_ssl()
provider = ssl.SSLContext
if os.name == 'nt':
    sys.executable = str(Path(python).with_name('pythonw.exe'))
with operation_control(threading.Event()):
    with certificates.package_trust_environment({}, python=python, node=sys.argv[1] or None) as values:
        path = Path(values['PIP_CERT'])
        context = ssl._ssl._SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(path))
        assert expected.issubset(context.get_ca_certs(binary_form=True))
        assert ssl.SSLContext is provider
        assert values['NODE_TLS_REJECT_UNAUTHORIZED'] == '1'
        assert values['NPM_CONFIG_STRICT_SSL'] == 'true'
    assert not path.exists()
print(json.dumps({'ready': True, 'provider_preserved': ssl.SSLContext is provider}))
'''
        result = subprocess.run([sys.executable, '-c', program, shutil.which('node') or ''],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ready': True, 'provider_preserved': True})

    def test_isolated_python_trust_probe_cannot_write_runtime_bytecode(self):
        with patch.object(certificates, '_tool_roots') as probe:
            certificates._python_roots(sys.executable, {})
        command = probe.call_args.args[0]
        result = subprocess.run([*command[:command.index('-c')], '-c',
                                 'import sys; print(sys.dont_write_bytecode)'],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'True')

    def test_native_export_filters_windows_roots_by_server_auth_without_changing_ssl(self):
        provider = ssl.SSLContext
        unsupported = Mock()
        unsupported.get_ca_certs.side_effect = NotImplementedError
        empty = self.root / 'empty.pem'
        empty.write_bytes(b'')
        stores = {
            'CA': [(self.roots[0], 'x509_asn', True),
                   (self.roots[2], 'x509_asn', {'1.3.6.1.5.5.7.3.2'})],
            'ROOT': [(self.roots[1], 'x509_asn', {'1.3.6.1.5.5.7.3.1'}),
                     (self.roots[3], 'pkcs_7_asn', True)],
        }
        with patch.dict('os.environ', {'SSL_CERT_FILE': str(empty), 'SSL_CERT_DIR': str(self.root)}), \
             patch.object(certificates.ssl, 'create_default_context', return_value=unsupported), \
             patch.object(sys, 'platform', 'win32'), \
             patch.object(ssl, 'enum_certificates', side_effect=stores.__getitem__, create=True), \
             certificates.package_trust_environment({}) as values:
            _, roots = self.read_bundle(values)
            self.assertEqual(roots, set(self.roots[:2]))
            self.assertIs(ssl.SSLContext, provider)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        if len(self.roots) < 4:
            self.skipTest('Requires at least four default trusted roots')

    def pem(self, index):
        return ssl.DER_cert_to_PEM_cert(self.roots[index])

    def ca_file(self, name, index):
        path = self.root / name
        path.write_text(self.pem(index), encoding='ascii')
        return path

    def context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=self.pem(0))
        return context

    def read_bundle(self, environment):
        path = Path(environment['PIP_CERT'])
        self.assertEqual(environment['NODE_EXTRA_CA_CERTS'], str(path))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(path))
        return path, set(context.get_ca_certs(binary_form=True))

    def test_system_pip_node_and_selected_roots_are_all_retained(self):
        selected = self.ca_file('selected.pem', 3)
        with patch.object(certificates.ssl, 'create_default_context', return_value=self.context()), \
             patch.object(certificates, '_python_roots', return_value=self.pem(1)), \
             patch.object(certificates, '_node_roots', return_value=self.pem(2)), \
             certificates.package_trust_environment({}, python='python', node='node', ca_file=selected) as values:
            path, roots = self.read_bundle(values)
            self.assertTrue(set(self.roots[:4]).issubset(roots))
            self.assertEqual(values['NPM_CONFIG_CAFILE'], str(path))
            self.assertEqual(values['NPM_CONFIG_STRICT_SSL'], 'true')
            self.assertEqual(values['NODE_TLS_REJECT_UNAUTHORIZED'], '1')
        self.assertFalse(path.exists())

    def test_no_selected_ca_uses_system_defaults_without_requiring_tools(self):
        with certificates.package_trust_environment({}) as values:
            _, roots = self.read_bundle(values)
            self.assertTrue(set(self.roots).issubset(roots))

    def test_ambient_extra_files_are_additive_without_allowing_npm_ca_replacement(self):
        pip_ca = self.ca_file('pip.pem', 1)
        node_ca = self.ca_file('node.pem', 2)
        inherited = {'PIP_CERT': str(pip_ca), 'NODE_EXTRA_CA_CERTS': str(node_ca),
                     'NPM_CONFIG_CA': 'untrusted-value', 'npm_config_cafile': '/invalid/override.pem'}
        with patch.object(certificates.ssl, 'create_default_context', return_value=self.context()), \
             patch.object(certificates, '_node_roots', return_value=self.pem(3)), \
             certificates.package_trust_environment(inherited, node='node') as values:
            path, roots = self.read_bundle(values)
            self.assertTrue(set(self.roots[:4]).issubset(roots))
            self.assertNotIn('NPM_CONFIG_CA', values)
            self.assertNotIn('npm_config_cafile', values)
            self.assertEqual(values['NPM_CONFIG_CAFILE'], str(path))

    def test_explicit_selected_ca_is_not_replaced_by_ambient_pip_file(self):
        selected = self.ca_file('selected.pem', 1)
        with patch.dict('os.environ', {'PIP_CERT': '/synthetic/absent.pem'}, clear=True), \
             certificates.package_trust_environment({}, ca_file=selected) as values:
            _, roots = self.read_bundle(values)
            self.assertIn(self.roots[1], roots)

    def test_invalid_ca_fails_before_tools_and_never_exposes_path(self):
        invalid = self.root / 'private-name.pem'
        invalid.write_text('not a PEM certificate', encoding='ascii')
        for selected in (invalid, self.root / 'missing.pem'):
            with self.subTest(selected=selected), \
                 patch.object(certificates, '_tool_roots') as tools, \
                 self.assertRaises(LauncherError) as raised:
                with certificates.package_trust_environment({}, ca_file=selected, python='python'):
                    self.fail('Invalid selected CA must fail closed')
            tools.assert_not_called()
            self.assertNotIn(str(selected), str(raised.exception))

    def test_bundle_is_removed_even_when_package_installation_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'package failed'):
            with certificates.package_trust_environment({}) as values:
                path = Path(values['PIP_CERT'])
                self.assertTrue(path.is_file())
                raise RuntimeError('package failed')
        self.assertFalse(path.exists())

    def test_target_pip_roots_are_read_locally_and_preserved(self):
        with certificates.package_trust_environment({}, python=sys.executable) as values:
            _, roots = self.read_bundle(values)
        from pip._vendor import certifi
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=certifi.where())
        self.assertTrue(set(context.get_ca_certs(binary_form=True)).issubset(roots))

    def test_pip_effective_verification_cannot_replace_union_with_ambient_bundle(self):
        from pip._internal.network.session import PipSession

        selected = self.ca_file('selected.pem', 1)
        ambient = self.ca_file('ambient.pem', 2)
        for inherited in ({'REQUESTS_CA_BUNDLE': str(ambient), 'CURL_CA_BUNDLE': str(ambient)},
                          {'CURL_CA_BUNDLE': str(ambient)}):
            with self.subTest(inherited=tuple(inherited)), \
                 patch.dict('os.environ', inherited, clear=True), \
                 certificates.package_trust_environment({}, ca_file=selected) as values, \
                 patch.dict('os.environ', values), \
                 PipSession() as session:
                session.verify = values['PIP_CERT']
                effective = session.merge_environment_settings('https://packages.invalid/simple/',
                                                               {}, None, None, None)
                self.assertEqual(effective['verify'], values['PIP_CERT'])
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.load_verify_locations(cafile=effective['verify'])
                self.assertTrue(set(self.roots).issubset(context.get_ca_certs(binary_form=True)))

    @unittest.skipUnless(shutil.which('node'), 'Requires an installed Node runtime')
    def test_node_export_is_complete_and_builtin_roots_are_preserved(self):
        exported = certificates._node_roots(shutil.which('node'), {})
        self.assertGreater(len(exported), 65536)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=exported)
        with certificates.package_trust_environment({}, node=shutil.which('node')) as values:
            _, roots = self.read_bundle(values)
        self.assertTrue(set(context.get_ca_certs(binary_form=True)).issubset(roots))

    def test_tool_failures_never_expose_internal_diagnostics(self):
        for result in (subprocess.CompletedProcess([], 1, '', 'synthetic-private-detail'),
                       subprocess.CompletedProcess([], 0, '', 'synthetic-private-detail')):
            with self.subTest(returncode=result.returncode), \
                 patch.object(certificates, 'controlled_run', return_value=result), \
                 self.assertRaises(LauncherError) as raised:
                certificates._tool_roots(['local-tool'], {})
            self.assertNotIn('synthetic-private-detail', str(raised.exception))

    def test_ascii_certificate_export_is_not_broken_by_legacy_stderr_bytes(self):
        program = 'import os,sys; os.write(1, sys.argv[1].encode("ascii")); os.write(2, b"\\x81\\xfe")'
        exported = certificates._tool_roots([sys.executable, '-c', program, self.pem(0)], {})
        self.assertEqual(exported, self.pem(0))

    def test_invalid_tool_output_is_rejected_and_cancellation_is_preserved(self):
        from scripts.launcher.process import OperationCancelled
        invalid = subprocess.CompletedProcess([], 0, b'\x81', b'synthetic-private-detail')
        with patch.object(certificates, 'controlled_run', return_value=invalid), \
             self.assertRaises(certificates.PackageTrustError) as caught:
            certificates._tool_roots(['tool'], {}, stage='node')
        self.assertEqual(caught.exception.code, 'package_trust_node')
        self.assertIn('UnicodeError', str(caught.exception))
        self.assertNotIn('synthetic-private-detail', str(caught.exception))
        with patch.object(certificates, 'controlled_run', side_effect=OperationCancelled()), \
             self.assertRaises(OperationCancelled):
            certificates._tool_roots(['tool'], {})

    def test_trust_failure_reaches_manager_with_exact_stage_and_safe_exception_type(self):
        from scripts.manager import operations
        cases = (
            ('export_context', NotImplementedError('synthetic-private-detail'), 'system', 'NotImplementedError'),
            ('_python_roots', TypeError('synthetic-private-detail'), 'python', 'TypeError'),
            ('_node_roots', RuntimeError('synthetic-private-detail'), 'node', 'RuntimeError'),
        )
        for method, failure, stage, diagnostic in cases:
            def dispatch(action, args, emit):
                with certificates.package_trust_environment({}, python=sys.executable,
                                                            node='diagnostic-node-fixture'):
                    self.fail('An invalid trust store must not reach package installation')
            with self.subTest(stage=stage), \
                 patch.object(certificates, method, side_effect=failure), \
                 patch.object(operations, '_dispatch', side_effect=dispatch):
                events = []
                operations.execute({'action': 'ensure'}, events.append, lambda: None, threading.Event())
                error = next(event for event in events if event['type'] == 'error')
                self.assertEqual(error['code'], 'package_trust_' + stage)
                self.assertIn(diagnostic, error['message'])
                self.assertNotIn('synthetic-private-detail', json.dumps(events))
                self.assertEqual(events[-1], {'type': 'done', 'ok': False})


if __name__ == '__main__':
    unittest.main()
