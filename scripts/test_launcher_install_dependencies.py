"""Source fallback must not disguise installation or integrity failures."""

import subprocess
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.launcher.model import LauncherError
from scripts.launcher.installation_sources import SourceSettings
from scripts.test_launcher import create_project


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
