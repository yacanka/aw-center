"""Corporate pip proxy settings survive source isolation without weakening it."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation_dependencies as dependencies
from scripts.launcher.process import OperationCancelled
from scripts.launcher_test_support import create_project


class PythonPackageNetworkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = create_project(self.root)
        self.config = self.root / 'pip.ini'
        self.config.write_text('[global]\nproxy =\n[wheel]\nproxy =\n', encoding='utf-8')
        selected_environment = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith('PIP_')
        }
        selected_environment['PIP_CONFIG_FILE'] = str(self.config)
        self.environment = patch.dict(os.environ, selected_environment, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def acquire(self):
        observed = {}
        real_run = dependencies.controlled_run

        def run(command, **options):
            if command[1:4] == ['-m', 'pip', 'wheel']:
                # Replace only the external package transfer. Configuration
                # discovery still executes the real pip under the chosen Python.
                observed.update(options['env'])
                return subprocess.CompletedProcess(command, 0, '', '')
            return real_run(command, **options)

        with patch.object(dependencies, 'controlled_run', side_effect=run):
            result = dependencies.capture(
                [sys.executable, '-m', 'pip', 'wheel', '--index-url',
                 'https://selected.invalid/simple', 'httpx==0.28.1'], self.project)
        self.assertEqual(result.returncode, 0)
        return observed

    def test_user_proxy_is_used_without_inheriting_extra_indexes_or_disabled_tls(self):
        proxy = 'http://fixture-user:fixture-password@proxy.invalid:8080'
        self.config.write_text(
            '[global]\nproxy = ' + proxy + '\n'
            'index-url = https://unselected.invalid/simple\n'
            'extra-index-url = https://unselected.invalid/extra\n'
            'trusted-host = unselected.invalid\n', encoding='utf-8')
        observed = self.acquire()
        self.assertEqual(observed.get('PIP_PROXY'), proxy)
        self.assertEqual(observed['PIP_CONFIG_FILE'], os.devnull)
        for name in ('PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL', 'PIP_TRUSTED_HOST'):
            self.assertNotIn(name, observed)

    def test_explicit_proxy_takes_precedence_over_file_and_wheel_settings(self):
        self.config.write_text(
            '[global]\nproxy = http://global.invalid:8080\n'
            '[wheel]\nproxy = http://wheel.invalid:8080\n', encoding='utf-8')
        with patch.dict(os.environ, {'PIP_PROXY': 'http://explicit.invalid:8080'}):
            observed = self.acquire()
        self.assertEqual(observed.get('PIP_PROXY'), 'http://explicit.invalid:8080')

    def test_wheel_proxy_takes_precedence_over_global_setting(self):
        self.config.write_text(
            '[global]\nproxy = http://global.invalid:8080\n'
            '[wheel]\nproxy = http://wheel.invalid:8080\n', encoding='utf-8')
        self.assertEqual(self.acquire().get('PIP_PROXY'), 'http://wheel.invalid:8080')

    def test_empty_proxy_overrides_preserve_pips_configured_global_proxy(self):
        self.config.write_text(
            '[global]\nproxy = http://global.invalid:8080\n[wheel]\nproxy =\n', encoding='utf-8')
        for empty in ('', '   '):
            with self.subTest(empty=repr(empty)), patch.dict(os.environ, {'PIP_PROXY': empty}):
                self.assertEqual(self.acquire().get('PIP_PROXY'), 'http://global.invalid:8080')

    def test_proxy_lookup_supports_pip_versions_with_file_grouped_items(self):
        self.config.write_text('[global]\nproxy = http://global.invalid:8080\n', encoding='utf-8')
        real_run = dependencies.controlled_run

        def grouped_items(command, **options):
            # pip 25.3+ groups items() by config file; get_value() retains its
            # key-based contract. Exercise that dependency shape in the child.
            command = list(command)
            script_index = command.index('-c') + 1
            command[script_index] = (
                'from pip._internal.configuration import Configuration; '
                'original_items = Configuration.items; '
                'Configuration.items = lambda self: [("pip.ini", dict(original_items(self)))];\n'
                + command[script_index])
            return real_run(command, **options)

        with patch.object(dependencies, 'controlled_run', side_effect=grouped_items):
            self.assertEqual(self.acquire().get('PIP_PROXY'), 'http://global.invalid:8080')

    def test_no_configured_proxy_preserves_environment_proxy_and_bounded_wait(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://network.invalid:8080'}):
            observed = self.acquire()
        self.assertFalse(observed.get('PIP_PROXY'))
        self.assertEqual(observed['HTTPS_PROXY'], 'http://network.invalid:8080')
        self.assertGreaterEqual(float(observed['PIP_DEFAULT_TIMEOUT']), 60)
        self.assertLessEqual(float(observed['PIP_DEFAULT_TIMEOUT']), 120)
        self.assertEqual(observed['PIP_RETRIES'], '3')

    def test_proxy_discovery_failure_does_not_expose_config_or_run_acquisition(self):
        private = 'fixture-user:fixture-password@proxy.invalid'
        acquisitions = []

        def run(command, **options):
            if command[1:4] == ['-m', 'pip', 'wheel']:
                acquisitions.append(command)
                return subprocess.CompletedProcess(command, 0, '', '')
            return subprocess.CompletedProcess(command, 1, private, private)

        with patch.object(dependencies, 'controlled_run', side_effect=run):
            with self.assertRaises(dependencies.LauncherError) as caught:
                dependencies.capture([sys.executable, '-m', 'pip', 'wheel', 'httpx==0.28.1'], self.project)
        self.assertEqual(getattr(caught.exception, 'code', None), 'package_proxy_config_failed')
        self.assertNotIn(private, str(caught.exception) + caught.exception.remedy)
        self.assertEqual(acquisitions, [])

    def test_malformed_proxy_response_is_rejected_without_private_diagnostics(self):
        for output in ('not-json-fixture', 'null', '"http://proxy.invalid\\nfixture"', '"' + 'x' * 17000 + '"'):
            with self.subTest(output_length=len(output)), \
                 patch.object(dependencies, 'controlled_run', return_value=
                              subprocess.CompletedProcess([], 0, output, 'private-fixture')):
                with self.assertRaises(dependencies.LauncherError) as caught:
                    dependencies.capture([sys.executable, '-m', 'pip', 'wheel'], self.project)
            self.assertEqual(getattr(caught.exception, 'code', None), 'package_proxy_config_failed')
            self.assertNotIn('fixture', str(caught.exception) + caught.exception.remedy)

    def test_proxy_lookup_timeout_and_cancellation_remain_distinct(self):
        failures = (
            (subprocess.TimeoutExpired(['private-fixture'], 15), dependencies.PackageProxyConfigError),
            (OperationCancelled(), OperationCancelled),
        )
        for failure, expected in failures:
            with self.subTest(error=type(failure).__name__), \
                 patch.object(dependencies, 'controlled_run', side_effect=failure):
                with self.assertRaises(expected):
                    dependencies.capture([sys.executable, '-m', 'pip', 'wheel'], self.project)

    def test_offline_install_does_not_read_proxy_configuration(self):
        self.config.write_text('invalid fixture config', encoding='utf-8')
        commands = []

        def run(command, **options):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, '', '')

        command = [sys.executable, '-m', 'pip', 'install', '--no-index', 'httpx==0.28.1']
        with patch.object(dependencies, 'controlled_run', side_effect=run):
            result = dependencies.capture(command, self.project)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(commands, [command])


if __name__ == '__main__':
    unittest.main()
