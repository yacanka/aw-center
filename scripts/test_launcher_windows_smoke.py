"""Native CMD acceptance smokes; public runtime downloads are explicitly opt-in.

No licensed software, private assets, SMTP or corporate integration is exercised.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.launcher.installation_permissions import require_private, secure_path
from scripts.launcher.installation_sources import load_catalog
from scripts.launcher.model import LauncherError


ROOT = Path(__file__).resolve().parents[1]


class WindowsWorkflowContractTests(unittest.TestCase):
    def test_native_installation_smoke_is_ci_opt_in_with_cmd_shell(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        native = workflow.split('  windows-native:', 1)[1].split('\n  container:', 1)[0]
        self.assertIn('AWCENTER_RUN_WINDOWS_INSTALL_SMOKE: "1"', native)
        self.assertIn('scripts.test_launcher_windows_smoke', native)
        self.assertIn('shell: cmd', native)
        self.assertIn('Build and verify Windows frontend artifact', native)


@unittest.skipUnless(os.name == 'nt', 'Requires native Windows CMD and Win32 ACL APIs')
class WindowsCommandSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='AW Center smoke ! ')
        self.addCleanup(self.temporary.cleanup)
        self.local = Path(self.temporary.name).resolve()
        self.home = self.local / 'AWCenter'
        system = Path(os.environ['SystemRoot'])
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(('AWCENTER_', 'DJANGO_', 'PYTHON', 'DATABASE_', 'CACHE_', 'JIRA_', 'DOORS_', 'DOCPROOF_', 'TEAMCENTER_', 'NUMARATOR_', 'AI_API_', 'EMAIL_'))
            and key not in {'SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS', 'IPV4_ADDRESS', 'PORT'}
        }
        self.environment.update(LOCALAPPDATA=str(self.local), PATH=os.pathsep.join((str(system / 'System32'), str(system))), PYTHONDONTWRITEBYTECODE='1')
        self.cmd = str(system / 'System32/cmd.exe')
        for tool in ('python', 'python3', 'node', 'npm', 'git'):
            self.assertIsNone(shutil.which(tool, path=self.environment['PATH']))

    def command(self, *arguments, timeout=30):
        # Arguments here are fixed test literals. Pass the complete CMD quoting
        # form directly to CreateProcess so Python does not escape CMD's quotes.
        command = f'"{self.cmd}" /d /s /c ""{ROOT / "AWCenter.cmd"}" {" ".join(arguments)}"'
        return subprocess.run(command, cwd=ROOT, env=self.environment, capture_output=True,
                              text=True, errors='replace', check=False, timeout=timeout)

    def test_help_has_no_runtime_or_private_home_side_effects(self):
        result = self.command('--help')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('AW Center', result.stdout)
        self.assertFalse(self.home.exists())

    def test_doctor_without_managed_python_is_read_only_and_refuses_start(self):
        result = self.command('doctor', '--profile', 'dev')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Managed Python', result.stdout)
        self.assertFalse(self.home.exists())

    def test_exact_owner_acl_is_verified_and_restricts_inheritance(self):
        path = self.local / 'private'
        path.mkdir()
        secure_path(path)
        require_private(path)
        secret = path / 'configuration.env'
        secret.write_text('fixture=true\n', encoding='utf-8')
        # A newly inherited ACE is deliberately converted to the exact explicit
        # protected file DACL before writing a real profile's private settings.
        secure_path(secret)
        require_private(secret)
        self.assertEqual(secret.read_text(encoding='utf-8'), 'fixture=true\n')

    def test_junction_ancestor_is_rejected_without_following_target(self):
        from scripts.launcher.installation_permissions import require_unlinked
        target = self.local / 'target'
        target.mkdir()
        junction = self.local / 'junction'
        command = f'"{self.cmd}" /d /s /c "mklink /J \"{junction}\" \"{target}\""'
        result = subprocess.run(command, env=self.environment, capture_output=True,
                                text=True, check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            with self.assertRaises(LauncherError):
                require_unlinked(junction / 'profile.env')
            self.assertEqual(list(target.iterdir()), [])
        finally:
            junction.rmdir()

    @unittest.skipUnless(os.environ.get('AWCENTER_RUN_WINDOWS_INSTALL_SMOKE') == '1',
                         'Set AWCENTER_RUN_WINDOWS_INSTALL_SMOKE=1 to download pinned native runtimes')
    def test_verified_bootstrap_toolchain_and_read_only_repeat_doctor(self):
        catalog = load_catalog()
        result = self.command('start', '--profile', 'dev', timeout=900)
        # Python bootstraps, then the Python launcher must refuse absent profile.
        self.assertNotEqual(result.returncode, 0)
        python = self.home / 'runtimes' / ('python-' + catalog['python'].version) / catalog['python'].executable
        archive = self.home / 'cache/runtimes' / catalog['python'].filename
        self.assertTrue(python.is_file(), result.stdout + result.stderr)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), catalog['python'].sha256)
        version = subprocess.run([str(python), '-I', '--version'], env=self.environment,
                                 capture_output=True, text=True, check=False, timeout=30)
        self.assertEqual(version.stdout.strip(), 'Python ' + catalog['python'].version)
        # Force the public-source transport to fail, then authenticate the same
        # archive from an explicit offline directory. No unreviewed bytes execute.
        offline = self.local / 'offline packages'
        offline.mkdir()
        shutil.copyfile(archive, offline / catalog['python'].filename)
        fallback_local = self.local / 'fallback user'
        fallback_local.mkdir()
        with mock.patch.dict(self.environment, {'LOCALAPPDATA': str(fallback_local),
                                                'HTTPS_PROXY': 'http://127.0.0.1:9'}):
            fallback = self.command('start', '--profile', 'dev', '--offline-dir',
                                    f'"{offline}"', timeout=120)
        fallback_python = fallback_local / 'AWCenter/runtimes' / ('python-' + catalog['python'].version) / catalog['python'].executable
        self.assertTrue(fallback_python.is_file(), fallback.stdout + fallback.stderr)
        rejected_local = self.local / 'rejected user'
        rejected_archive = rejected_local / 'AWCenter/cache/runtimes' / catalog['python'].filename
        rejected_archive.parent.mkdir(parents=True)
        rejected_archive.write_bytes(b'fixture: corrupt archive must never execute')
        with mock.patch.dict(self.environment, {'LOCALAPPDATA': str(rejected_local)}):
            rejected = self.command('start', '--profile', 'dev')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('integrity', rejected.stdout.lower())
        self.assertFalse((rejected_local / 'AWCenter/runtimes').exists())
        self.assertFalse((self.home / 'config').exists())
        # An explicit toolchain setup verifies Python's full archive inventory,
        # Node and the repository npm pin. No application dependencies or DB.
        probe = (
            'import json; from pathlib import Path; '
            'from scripts.launcher.toolchain import ensure_toolchain, inspect_toolchain; '
            'from scripts.launcher.installation_sources import SourceSettings; '
            f'h=Path({str(self.home)!r}); ensure_toolchain(h, SourceSettings()); '
            'print(json.dumps(inspect_toolchain(h)))'
        )
        toolchain = subprocess.run([str(python), '-I', '-B', '-c',
                                   'import sys; sys.path.insert(0, ' + repr(str(ROOT)) + '); ' + probe],
                                  cwd=ROOT, env=self.environment, capture_output=True,
                                  text=True, check=False, timeout=900)
        self.assertEqual(toolchain.returncode, 0, toolchain.stdout + toolchain.stderr)
        self.assertTrue(all(row['status'] == 'ready' for row in json.loads(toolchain.stdout)))
        before = {str(path): (path.stat().st_size, path.stat().st_mtime_ns)
                  for path in self.home.rglob('*')}
        result = self.command('doctor', '--profile', 'dev')
        self.assertNotEqual(result.returncode, 0)
        after = {str(path): (path.stat().st_size, path.stat().st_mtime_ns)
                 for path in self.home.rglob('*')}
        self.assertEqual(after, before)
        self.assertFalse((self.home / 'config').exists())


class ReadinessTeardownSmokeTests(unittest.TestCase):
    def test_failed_readiness_terminates_owned_real_child(self):
        from scripts.launcher.installation_readiness import wait_until_ready
        from scripts.launcher.process import start, terminate
        from scripts.launcher.runtime import dev
        from scripts.launcher.model import Scope
        from scripts.test_launcher import create_project

        process = start([sys.executable, '-c', 'import time; time.sleep(30)'], ROOT)
        try:
            profile = {'name': 'dev', 'host': '127.0.0.1', 'backend_port': 8000,
                       'frontend_port': 5173}
            with tempfile.TemporaryDirectory() as temporary:
                project = create_project(Path(temporary))
                with mock.patch('scripts.launcher.installation_readiness.probe_http', return_value=False), \
                     mock.patch('scripts.launcher.runtime.require_runtime_ports'), \
                     mock.patch('scripts.launcher.runtime.start_backend', return_value=process), \
                     mock.patch('scripts.launcher.runtime.start_job_workers', return_value=[]):
                    with self.assertRaises(LauncherError):
                        dev(project, Scope(frontend=False), host='127.0.0.1', backend_port=8000,
                            frontend_port=5173, no_backend_reload=True, migrate=False,
                            ready=lambda owned: wait_until_ready(owned, profile, Path(temporary), timeout=0.01))
                self.assertIsNotNone(process.poll(), 'Runtime readiness failure leaked its owned child')
        finally:
            if process.poll() is None:
                terminate([process])


if __name__ == '__main__':
    unittest.main()
