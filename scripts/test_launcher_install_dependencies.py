"""Source fallback must not disguise installation or integrity failures."""

import json
import os
import shutil
import subprocess
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.launcher.model import LauncherError
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher_test_support import create_project


class PackageConfigurationIsolationTests(unittest.TestCase):
    def test_capture_provides_distinct_empty_npm_configs_and_removes_them_after_exit(self):
        from scripts.launcher.installation_dependencies import capture
        program = '''import json, os, pathlib, sys
paths = [os.environ['NPM_CONFIG_USERCONFIG'], os.environ['NPM_CONFIG_GLOBALCONFIG']]
print(json.dumps({'paths': paths, 'contents': [pathlib.Path(path).read_text() for path in paths],
                  'inherited': any(name in os.environ for name in ('NPM_CONFIG_REGISTRY', 'npm_config_registry', 'NPM_CONFIG__AUTH', 'PIP_INDEX_URL'))}))
sys.exit(int(sys.argv[1]))
'''
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            for exit_code in (0, 7):
                with self.subTest(exit_code=exit_code), \
                     mock.patch.dict(os.environ, {'NPM_CONFIG_REGISTRY': 'https://untrusted.invalid',
                                                 'npm_config_registry': 'https://untrusted.invalid',
                                                 'NPM_CONFIG__AUTH': 'inherited-credential-fixture',
                                                 'PIP_INDEX_URL': 'https://untrusted.invalid'}):
                    result = capture([sys.executable, '-c', program, str(exit_code)], project)
                    self.assertEqual(result.returncode, exit_code)
                    observed = json.loads(result.stdout)
                    self.assertNotEqual(*observed['paths'])
                    self.assertEqual(observed['contents'], ['', ''])
                    self.assertFalse(observed['inherited'])
                    self.assertTrue(all(not Path(path).exists() for path in observed['paths']))

    def test_capture_cleans_npm_configs_after_start_error_timeout_and_cancellation(self):
        from scripts.launcher import installation_dependencies as dependencies
        from scripts.launcher.process import OperationCancelled
        cases = ((OSError('fixture'), OSError),
                 (subprocess.TimeoutExpired(['fixture'], 1), LauncherError),
                 (OperationCancelled('fixture'), OperationCancelled))
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            for error, expected in cases:
                observed = []
                def fail(command, **options):
                    paths = [Path(options['env'][name]) for name in
                             ('NPM_CONFIG_USERCONFIG', 'NPM_CONFIG_GLOBALCONFIG')]
                    self.assertNotEqual(*paths)
                    self.assertTrue(all(path.is_file() and path.read_bytes() == b'' for path in paths))
                    observed.extend(paths)
                    raise error
                with self.subTest(error=type(error).__name__), \
                     mock.patch.object(dependencies, 'controlled_run', side_effect=fail):
                    with self.assertRaises(expected):
                        dependencies.capture(['fixture'], project)
                self.assertEqual(len(observed), 2)
                self.assertTrue(all(not path.exists() for path in observed))

    def test_capture_preserves_explicit_package_config_overrides(self):
        from scripts.launcher.installation_dependencies import capture
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_project(root)
            user, global_config = root / 'selected-user.npmrc', root / 'selected-global.npmrc'
            for path in (user, global_config):
                path.write_bytes(b'')
            result = capture([sys.executable, '-c',
                              'import json, os; print(json.dumps([os.environ["NPM_CONFIG_USERCONFIG"], os.environ["NPM_CONFIG_GLOBALCONFIG"]]))'],
                             project, {'NPM_CONFIG_USERCONFIG': str(user),
                                       'NPM_CONFIG_GLOBALCONFIG': str(global_config)})
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), [str(user), str(global_config)])
            self.assertTrue(user.is_file() and global_config.is_file())

    @unittest.skipUnless(shutil.which('node'), 'A local Node executable is required for real npm tests')
    def test_real_npm_version_runs_with_isolated_capture_configuration(self):
        from scripts.launcher.installation_dependencies import capture
        from scripts.launcher.system_node import _npm_candidates
        node = Path(shutil.which('node')).resolve()
        cli = next((path for path in _npm_candidates(node) if path.is_file()), None)
        if cli is None:
            self.skipTest('An npm CLI beside local Node is required')
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            result = capture([node, cli, '--version'], project, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip(), r'^\d+\.\d+\.\d+$')


class AcquisitionFailureTests(unittest.TestCase):
    def test_install_adds_system_trust_with_and_without_selected_ca(self):
        from scripts.launcher import installation_dependencies as dependencies

        roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        if not roots:
            self.skipTest('Requires a default trusted CA')
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            ca_file = Path(temporary) / 'corporate.pem'
            ca_file.write_text(ssl.DER_cert_to_PEM_cert(roots[0]), encoding='ascii')
            for selected in (None, ca_file):
                observed = []
                def packages(project, settings, tool_env, stage):
                    bundle = Path(tool_env['NODE_EXTRA_CA_CERTS'])
                    self.assertTrue(bundle.is_file())
                    self.assertEqual(tool_env['PIP_CERT'], str(bundle))
                    self.assertNotEqual(bundle, ca_file)
                    self.assertEqual(tool_env['NPM_CONFIG_CAFILE'], str(bundle))
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.load_verify_locations(cafile=str(bundle))
                    self.assertTrue(set(roots).issubset(context.get_ca_certs(binary_form=True)))
                    observed.append(bundle)
                with self.subTest(selected=selected), \
                     mock.patch.object(dependencies, '_ensure_venv'), \
                     mock.patch('scripts.launcher.certificates._python_roots', return_value=ssl.DER_cert_to_PEM_cert(roots[0])), \
                     mock.patch.object(dependencies, '_python_packages', side_effect=packages), \
                     mock.patch.object(dependencies, '_frontend_packages', side_effect=packages):
                    import sys
                    dependencies.install_dependencies(project, SourceSettings(ca_file=selected),
                                                       {'AWCENTER_MANAGED_PYTHON': sys.executable})
                self.assertEqual(len(observed), 2)
                self.assertFalse(observed[0].exists())

    def test_only_availability_failures_allow_package_source_fallback(self):
        from scripts.launcher.installation_dependencies import availability_failure

        for message in ("NewConnectionError: connection refused", "npm ERR! code ENOTFOUND",
                        "ReadTimeoutError", "HTTP error 404", "503 Service Unavailable"):
            with self.subTest(message=message):
                self.assertTrue(availability_failure(message))
        for message in ("CERTIFICATE_VERIFY_FAILED", "npm ERR! code EINTEGRITY",
                        "ERROR: Failed building wheel", "No space left on device",
                        "ERESOLVE unable to resolve dependency tree", "Access is denied"):
            with self.subTest(message=message):
                self.assertFalse(availability_failure(message))

    def test_offline_npm_cache_is_copied_before_installation(self):
        from scripts.launcher.installation_dependencies import _frontend_packages

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_project(root)
            (project.frontend / "package-lock.json").write_text("{}", encoding="utf-8")
            offline = root / "offline"
            (offline / "npm-cache").mkdir(parents=True)
            (offline / "npm-cache" / "fixture").write_text("immutable", encoding="utf-8")
            stage = root / "stage"
            stage.mkdir()
            calls = []

            def capture(command, *_):
                calls.append(command)
                if "--offline" not in command:
                    return subprocess.CompletedProcess(command, 1, "", "npm ERR! code ENOTFOUND")
                cache = Path(command[command.index("--cache") + 1])
                self.assertNotEqual(cache, offline / "npm-cache")
                (cache / "npm-log").write_text("mutable", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch("scripts.launcher.installation_dependencies._npm_command", return_value=["npm"]), \
                 mock.patch("scripts.launcher.installation_dependencies._offline_dependencies", return_value=offline), \
                 mock.patch("scripts.launcher.installation_dependencies.capture", side_effect=capture):
                _frontend_packages(project, SourceSettings(offline_dir=offline), {}, stage)
            self.assertEqual([path.name for path in (offline / "npm-cache").iterdir()], ["fixture"])
            self.assertEqual(len(calls), 2)

    def test_integrity_failure_does_not_try_another_registry(self):
        from scripts.launcher.installation_dependencies import _frontend_packages

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_project(root)
            (project.frontend / "package-lock.json").write_text("{}", encoding="utf-8")
            with mock.patch("scripts.launcher.installation_dependencies._npm_command", return_value=["npm"]), \
                 mock.patch("scripts.launcher.installation_dependencies.capture", return_value=
                            subprocess.CompletedProcess([], 1, "", "EINTEGRITY")) as capture:
                with self.assertRaises(LauncherError):
                    _frontend_packages(project, SourceSettings(npm_registry_url="https://mirror.example"), {}, root)
            self.assertEqual(capture.call_count, 1)


if __name__ == "__main__":
    unittest.main()
