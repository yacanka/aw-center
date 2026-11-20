"""A console-prepared Dev checkout can be opened without repackaging it."""
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation_dependencies as packages
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher_test_support import create_project


class ConsolePackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = create_project(Path(temporary.name).resolve())
        self.base = Path(sys._base_executable).resolve()
        subprocess.run([self.base, '-m', 'venv', '--without-pip', '--copies', self.project.venv], check=True)
        site = Path(sysconfig.get_path('purelib', scheme='venv', vars={
            'base': str(self.project.venv), 'platbase': str(self.project.venv)}))
        self.metadata = site / 'Django-5.2.dist-info' / 'METADATA'
        self.metadata.parent.mkdir(parents=True)
        self.metadata.write_text('Metadata-Version: 2.1\nName: Django\nVersion: 5.2\n')
        self.project.requirements.write_text("Django==5.2\nunused==1 ; python_version < '3'\n")
        self.modules = self.project.frontend / 'node_modules'
        self.vite = self.modules / 'vite/bin/vite.js'
        self.vite.parent.mkdir(parents=True)
        self.vite.write_text('console installation')
        self.lock = self.project.frontend / 'package-lock.json'
        entries = {'node_modules/vite': {'version': '8.3.7', 'integrity': 'test-hash'}}
        self.lock.write_text(json.dumps({'lockfileVersion': 3, 'packages': {'': {}, **entries}}))
        self.npm_record = self.modules / '.package-lock.json'
        self.npm_record.write_text(json.dumps({'lockfileVersion': 3, 'packages': entries}))

    def install(self):
        packages.install_dependencies(self.project, SourceSettings(mode='offline'),
            {'AWCENTER_MANAGED_PYTHON': str(self.base), 'AWCENTER_MANAGED_NODE': 'unused'},
            expected_python=self.base,
            repair_packages=True, reuse_current_packages=True, use_local_packages=True)

    def test_existing_console_packages_survive_first_open_and_only_fast_dev_reuses_them(self):
        original = self.project.python.stat()
        with patch.object(packages, '_package_inventory', side_effect=AssertionError('scanned installed tree')):
            self.install()
            ready = packages.dependency_checks(self.project, developer=True, use_local_packages=True)
            self.assertEqual([row['status'] for row in ready], ['ready', 'ready'])
            strict = packages.dependency_checks(self.project)
            self.assertEqual([row['status'] for row in strict], ['missing', 'missing'])
            self.lock.write_text('{"lockfileVersion": 3, "packages": {}}')
            ready = packages.dependency_checks(self.project, developer=True, use_local_packages=True)
            self.assertEqual([row['status'] for row in ready], ['ready', 'missing'])
        self.assertEqual(self.project.python.stat().st_ino, original.st_ino)
        self.assertEqual(self.project.python.stat().st_mtime_ns, original.st_mtime_ns)
        self.assertEqual(self.vite.read_text(), 'console installation')
        self.assertFalse((self.project.root / '.runtime/venv-backups').exists())

    def test_mismatched_python_or_npm_metadata_cannot_authorize_local_reuse(self):
        self.metadata.write_text('Metadata-Version: 2.1\nName: Django\nVersion: 4.2\n')
        self.npm_record.write_text('{"lockfileVersion": 3, "packages": {}}')
        with patch.object(packages, '_prepare_package_venv', side_effect=lambda *args: args[-1]), \
             patch.object(packages, 'package_trust_environment', side_effect=packages.PackageTimeoutError):
            with self.assertRaises(packages.PackageTimeoutError):
                self.install()
        rows = packages.dependency_checks(self.project, developer=True, use_local_packages=True)
        self.assertEqual([row['status'] for row in rows], ['missing', 'missing'])

    def test_removing_a_python_distribution_invalidates_only_the_local_python_hint(self):
        self.install()
        self.metadata.unlink()
        self.metadata.parent.rmdir()
        rows = packages.dependency_checks(self.project, developer=True, use_local_packages=True)
        self.assertEqual([row['status'] for row in rows], ['missing', 'ready'])

    def test_base_python_does_not_need_a_global_pip_installation(self):
        capture = packages.capture
        def without_site_packages(command, *args, **kwargs):
            return capture([command[0], '-S', *command[1:]], *args, **kwargs)
        with patch.object(packages, 'capture', side_effect=without_site_packages):
            self.assertTrue(packages._console_python_packages_match(self.project, self.base, {}))

    def test_console_npm_install_requires_the_windows_x64_native_packages(self):
        manifest = json.loads(self.lock.read_text())
        native = {'version': '1', 'optional': True, 'os': ['win32'], 'cpu': ['x64']}
        manifest['packages']['node_modules/windows-binding'] = native
        self.lock.write_text(json.dumps(manifest))
        self.assertFalse(packages._console_frontend_packages_match(self.lock, self.npm_record))
        native['os'] = ['darwin']
        self.lock.write_text(json.dumps(manifest))
        self.assertTrue(packages._console_frontend_packages_match(self.lock, self.npm_record))

    def test_venv_pointing_to_another_python_home_is_not_adopted(self):
        config = self.project.venv / 'pyvenv.cfg'
        lines = config.read_text().splitlines()
        config.write_text('\n'.join('home = elsewhere' if line.startswith('home =') else line for line in lines))
        self.assertFalse(packages._console_python_packages_match(self.project, self.base, {}))
