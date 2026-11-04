"""Package trust unions retain native/tool roots without distributable PEM state."""

from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import certificates
from scripts.launcher.model import LauncherError


class PackageTrustTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
