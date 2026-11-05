"""Source-launched Manager recovery freezes exactly the selected source safely."""
from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts import build_manager
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher.installation_dependencies import PackageTimeoutError
from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled, operation_control
from scripts.manager.distribution import verify_distribution
from scripts.manager.payload import MANAGER_SOURCE_FILES
from scripts.test_launcher_bundle import project_at


class BuildRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = project_at(self.root / 'source')
        for relative in (*MANAGER_SOURCE_FILES, 'scripts/build_manager.py',
                         'packaging/manager.spec', 'packaging/manager-requirements.txt'):
            path = self.project.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text('# source fixture\n')
        self.destination = self.root / 'portable'

    def freeze(self, settings, capture):
        freeze = getattr(build_manager, 'freeze_manager', None)
        self.assertIsNotNone(freeze, 'Missing distributions must be built automatically')
        with patch.object(build_manager.sys, 'platform', 'win32'), \
             patch.object(build_manager.platform, 'machine', return_value='AMD64'), \
             patch('scripts.launcher.installation_dependencies.capture', side_effect=capture), \
             patch('scripts.launcher.certificates.package_trust_environment',
                   side_effect=lambda values, **kwargs: nullcontext({**values, 'PIP_CERT': 'approved-ca'})):
            return freeze(self.project, self.destination, settings, python=self.root / 'managed/python.exe')

    def commands(self, commands, *, failure=None):
        def capture(command, project, overrides=None, **kwargs):
            command = list(map(str, command))
            commands.append((command, overrides))
            if command[1:4] == ['-I', '-B', '-m'] and 'venv' in command:
                builder = Path(command[-1])
                (builder / 'Scripts').mkdir(parents=True)
                (builder / 'Scripts/python.exe').write_bytes(b'isolated Python')
            if 'pip' in command and 'download' in command and failure:
                return subprocess.CompletedProcess(command, 1, '', failure)
            if 'pip' in command and 'download' in command:
                wheels = Path(command[command.index('--dest') + 1])
                wheels.mkdir(parents=True, exist_ok=True)
                (wheels / 'PyInstaller.whl').write_bytes(b'approved wheel fixture')
            if 'PyInstaller' in command:
                frozen = Path(command[command.index('--distpath') + 1]) / 'AWCenterManager'
                (frozen / '_internal').mkdir(parents=True)
                (frozen / 'AWCenterManager.exe').write_bytes(b'new exe')
                (frozen / '_internal/python311.dll').write_bytes(b'embedded Python')
            return subprocess.CompletedProcess(command, 0, '', '')
        return capture

    def test_freeze_uses_managed_python_and_selected_index_without_mutating_app_venv(self):
        producer = self.project.root / '.venv/keep'
        producer.parent.mkdir()
        producer.write_bytes(b'app environment')
        commands = []
        settings = SourceSettings(mode='corporate', python_index_url='https://packages.example/simple')
        self.freeze(settings, self.commands(commands))
        manifest = verify_distribution(self.destination)
        self.assertFalse(manifest['complete'])
        self.assertEqual((self.destination / 'AWCenterManager.exe').read_bytes(), b'new exe')
        self.assertEqual(producer.read_bytes(), b'app environment')
        self.assertEqual(commands[0][0][0], str(self.root / 'managed/python.exe'))
        pip_commands = [(command, env) for command, env in commands if 'pip' in command]
        self.assertEqual(len(pip_commands), 2)
        command, environment = pip_commands[0]
        self.assertIn('download', command)
        self.assertEqual(command[command.index('--index-url') + 1], 'https://packages.example/simple')
        self.assertEqual(environment['PIP_CERT'], 'approved-ca')
        self.assertNotIn('https://pypi.org/simple', command)
        self.assertIn('--no-index', pip_commands[1][0])
        self.assertIn('install', pip_commands[1][0])
        self.assertEqual((self.destination / 'source/launcher.py').read_bytes(),
                         (self.project.root / 'launcher.py').read_bytes())

    def test_offline_recovery_never_contacts_an_index_or_publishes_partial_distribution(self):
        commands = []
        with self.assertRaises(LauncherError):
            self.freeze(SourceSettings(mode='offline'), self.commands(commands))
        self.assertFalse(any('pip' in command for command, _ in commands))
        self.assertFalse(self.destination.exists())

    def test_tls_failure_does_not_try_another_source_or_publish_a_distribution(self):
        commands = []
        settings = SourceSettings(mode='online', python_index_url='https://packages.example/simple')
        with self.assertRaises(LauncherError) as failed:
            self.freeze(settings, self.commands(commands, failure='SSLCertVerificationError private-secret'))
        self.assertEqual(failed.exception.code, 'package_tls_failed')
        self.assertNotIn('private-secret', str(failed.exception))
        self.assertEqual(sum('pip' in command for command, _ in commands), 1)
        self.assertFalse(self.destination.exists())

    def test_acquisition_timeout_tries_next_allowed_index_before_isolated_install(self):
        commands = []
        capture = self.commands(commands)
        timed_out = False
        def unavailable_once(command, project, overrides=None, **options):
            nonlocal timed_out
            if 'download' in command and not timed_out:
                timed_out = True
                commands.append((list(map(str, command)), overrides))
                raise PackageTimeoutError()
            return capture(command, project, overrides, **options)
        self.freeze(SourceSettings(mode='restricted', python_index_url='https://packages.example/simple'),
                    unavailable_once)
        downloads = [command for command, _ in commands if 'download' in command]
        self.assertEqual([command[command.index('--index-url') + 1] for command in downloads],
                         ['https://packages.example/simple', 'https://pypi.org/simple'])
        self.assertNotEqual(downloads[0][downloads[0].index('--dest') + 1],
                            downloads[1][downloads[1].index('--dest') + 1])
        installs = [command for command, _ in commands if 'install' in command]
        self.assertEqual(len(installs), 1)
        self.assertIn('--no-index', installs[0])
        verify_distribution(self.destination)

    def test_installation_failure_never_retries_other_indexes(self):
        commands = []
        capture = self.commands(commands)
        def unavailable_install(command, project, overrides=None, **options):
            result = capture(command, project, overrides, **options)
            if 'install' in command:
                return subprocess.CompletedProcess(command, 1, '', 'connection refused')
            return result
        with self.assertRaises(LauncherError):
            self.freeze(SourceSettings(mode='online', python_index_url='https://packages.example/simple'),
                        unavailable_install)
        self.assertEqual(sum('download' in command for command, _ in commands), 1)
        self.assertFalse(self.destination.exists())

    def test_build_subprocess_honors_manager_cancellation(self):
        stop = threading.Event()
        stop.set()
        with operation_control(stop):
            with self.assertRaises(OperationCancelled):
                build_manager._run_build([sys.executable, '-c', 'pass'], cwd=self.root,
                                         env={})


if __name__ == '__main__':
    unittest.main()
