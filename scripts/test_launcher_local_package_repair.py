"""Only the local Manager opt-in may replace verified-invalid package outputs."""
from contextlib import nullcontext
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation_dependencies as deps
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled
from scripts.launcher_test_support import create_project


class LocalPackageRepairTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = create_project(self.root)
        self.selected = self.root / 'selected-python.exe'
        self.selected.write_bytes(b'validated interpreter')
        self.tools = {'AWCENTER_MANAGED_PYTHON': str(self.selected),
                      'AWCENTER_MANAGED_NODE': str(self.root / 'selected-node.exe')}
        self.modules = self.project.frontend / 'node_modules'
        self.frontend_lock = self.project.frontend / 'package-lock.json'
        self.frontend_lock.write_bytes(b'{"lockfileVersion": 3}')
        self.project.python.parent.mkdir(parents=True)
        self.project.python.write_bytes(b'original interpreter')
        self.python_library = self.project.venv / 'library.py'
        self.frontend_library = self.modules / 'library.js'
        self.modules.mkdir()
        (self.modules / 'preserved.js').write_bytes(b'unmodified old frontend file')
        deps.dependency_stage(self.project.venv, self.project.requirements,
                              lambda: self.python_library.write_bytes(b'original Python package'))
        deps.dependency_stage(self.modules, self.frontend_lock,
                              lambda: self.frontend_library.write_bytes(b'original frontend package'))
        self.original_receipts = {
            target.name: (target / deps._STAGE_RECEIPT).read_bytes()
            for target in (self.project.venv, self.modules)
        }
        self.preserved_state = {}
        for relative, content in (
            ('backend/db.sqlite3', b'existing database fixture'),
            ('backend/.env', b'unchanged application settings fixture'),
            ('backend/private-media/document', b'existing private artifact fixture'),
            ('config/keys', b'existing key state fixture'),
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.preserved_state[path] = content
        self.interrupt_python = False
        self.interrupt_frontend = False

    def capture(self, command, *_args, **_kwargs):
        if command[1:3] == ['-m', 'venv']:
            self.project.python.parent.mkdir(parents=True, exist_ok=True)
            self.project.python.write_bytes(b'replacement interpreter')
        output = json.dumps(str(self.selected)) if '_base_executable' in str(command) else 'True'
        return subprocess.CompletedProcess(command, 0, output, '')

    def python_packages(self, *_args, **_kwargs):
        self.python_library.write_bytes(b'partial Python package' if self.interrupt_python
                                        else b'replacement Python package')
        if self.interrupt_python:
            raise OperationCancelled()

    def frontend_packages(self, *_args, **_kwargs):
        self.modules.mkdir(exist_ok=True)
        self.frontend_library.write_bytes(b'partial frontend package' if self.interrupt_frontend
                                          else b'replacement frontend package')
        if self.interrupt_frontend:
            raise OperationCancelled()

    def install(self, **options):
        with patch.object(deps, 'capture', side_effect=self.capture), \
             patch.object(deps, '_python_packages', side_effect=self.python_packages), \
             patch.object(deps, '_frontend_packages', side_effect=self.frontend_packages), \
             patch.object(deps, 'package_trust_environment', side_effect=lambda env, **_: nullcontext(env)):
            deps.install_dependencies(self.project, SourceSettings(mode='offline'), self.tools,
                                      expected_python=self.selected, repair_venv=True, **options)

    def backups(self, name):
        return list((self.root / '.runtime' / name).glob('*/.venv' if name == 'venv-backups'
                                                       else '*/node_modules'))

    def assert_application_state_unchanged(self):
        for path, content in self.preserved_state.items():
            self.assertEqual(path.read_bytes(), content)

    def test_missing_recorded_outputs_are_preserved_and_reinstalled_only_with_opt_in(self):
        self.python_library.unlink()
        self.frontend_library.unlink()

        self.install(repair_packages=True)

        self.assertEqual(self.python_library.read_bytes(), b'replacement Python package')
        self.assertEqual(self.frontend_library.read_bytes(), b'replacement frontend package')
        for name, target in (('venv-backups', self.project.venv), ('npm-backups', self.modules)):
            backups = self.backups(name)
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / deps._STAGE_RECEIPT).read_bytes(),
                             self.original_receipts[target.name])
        old_python = self.backups('venv-backups')[0] / self.project.python.relative_to(self.project.venv)
        self.assertEqual(old_python.read_bytes(), b'original interpreter')
        self.assertEqual((self.backups('npm-backups')[0] / 'preserved.js').read_bytes(),
                         b'unmodified old frontend file')
        self.assertFalse((self.modules / 'preserved.js').exists())
        self.assertEqual([row['status'] for row in deps.dependency_checks(self.project)], ['ready', 'ready'])
        self.assert_application_state_unchanged()

    def test_missing_entire_outputs_can_be_prepared_without_changing_application_state(self):
        shutil.rmtree(self.project.venv)
        shutil.rmtree(self.modules)

        self.install(repair_packages=True)

        self.assertEqual(self.python_library.read_bytes(), b'replacement Python package')
        self.assertEqual(self.frontend_library.read_bytes(), b'replacement frontend package')
        self.assertEqual(self.backups('venv-backups'), [])
        self.assertEqual(self.backups('npm-backups'), [])
        self.assert_application_state_unchanged()

    def test_default_is_strict_for_missing_recorded_python_and_frontend_outputs(self):
        for library, original in ((self.python_library, b'original Python package'),
                                  (self.frontend_library, b'original frontend package')):
            with self.subTest(library=library.name):
                library.unlink()
                with self.assertRaises(deps.DependencyIntegrityError):
                    self.install()
                self.assertEqual(self.project.python.read_bytes(), b'original interpreter')
                self.assertEqual(self.backups('venv-backups'), [])
                self.assertEqual(self.backups('npm-backups'), [])
                library.write_bytes(original)
        self.assert_application_state_unchanged()

    def test_interrupted_python_replacement_can_resume_with_original_backup_intact(self):
        self.python_library.unlink()
        self.interrupt_python = True
        with self.assertRaises(OperationCancelled):
            self.install(repair_packages=True)
        original = self.backups('venv-backups')[0]
        self.assertEqual((original / deps._STAGE_RECEIPT).read_bytes(), self.original_receipts['.venv'])
        self.assertFalse((self.project.venv / deps._STAGE_RECEIPT).exists())

        self.interrupt_python = False
        self.install(repair_packages=True)

        self.assertEqual(self.python_library.read_bytes(), b'replacement Python package')
        self.assertEqual((original / deps._STAGE_RECEIPT).read_bytes(), self.original_receipts['.venv'])
        self.assertEqual([row['status'] for row in deps.dependency_checks(self.project)], ['ready', 'ready'])
        self.assert_application_state_unchanged()

    def test_interrupted_frontend_replacement_can_resume_with_original_backup_intact(self):
        self.frontend_library.unlink()
        self.interrupt_frontend = True
        with self.assertRaises(OperationCancelled):
            self.install(repair_packages=True)
        original = self.backups('npm-backups')[0]
        self.assertEqual((original / deps._STAGE_RECEIPT).read_bytes(), self.original_receipts['node_modules'])

        self.interrupt_frontend = False
        self.install(repair_packages=True)

        self.assertEqual(self.frontend_library.read_bytes(), b'replacement frontend package')
        self.assertEqual((original / deps._STAGE_RECEIPT).read_bytes(), self.original_receipts['node_modules'])
        self.assertEqual([row['status'] for row in deps.dependency_checks(self.project)], ['ready', 'ready'])
        self.assert_application_state_unchanged()

    def test_unsafe_link_does_not_authorize_replacement(self):
        self.python_library.unlink()
        try:
            self.python_library.symlink_to(self.root / 'backend/.env')
        except OSError:
            self.skipTest('symlink privilege unavailable')
        with self.assertRaises(LauncherError):
            self.install(repair_packages=True)
        self.assertTrue(self.python_library.is_symlink())
        self.assertEqual(self.project.python.read_bytes(), b'original interpreter')
        self.assertEqual(self.backups('venv-backups'), [])
        self.assert_application_state_unchanged()

    def test_io_and_unknown_inventory_errors_do_not_authorize_replacement(self):
        for error in (PermissionError(13, 'private diagnostic'), OSError(5, 'private diagnostic'),
                      LauncherError('unrecognized inventory failure'), OperationCancelled()):
            with self.subTest(error=type(error).__name__), \
                 patch.object(deps, '_package_inventory', side_effect=error):
                with self.assertRaises(LauncherError):
                    self.install(repair_packages=True)
            self.assertEqual(self.project.python.read_bytes(), b'original interpreter')
            self.assertEqual(self.backups('venv-backups'), [])
            self.assertEqual(self.backups('npm-backups'), [])
        self.assert_application_state_unchanged()

    def test_missing_receipt_does_not_allow_archiving_an_unsafe_partial_tree(self):
        (self.modules / deps._STAGE_RECEIPT).unlink()
        self.frontend_library.unlink()
        try:
            self.frontend_library.symlink_to(self.root / 'backend/.env')
        except OSError:
            self.skipTest('symlink privilege unavailable')
        with self.assertRaises(LauncherError):
            self.install(repair_packages=True)
        self.assertTrue(self.frontend_library.is_symlink())
        self.assertEqual(self.backups('npm-backups'), [])
        self.assert_application_state_unchanged()

    def test_unrecognized_receipt_is_not_repair_evidence(self):
        (self.project.venv / deps._STAGE_RECEIPT).write_bytes(b'not a package receipt')
        with self.assertRaises(deps.DependencyIntegrityError):
            self.install(repair_packages=True)
        self.assertEqual(self.project.python.read_bytes(), b'original interpreter')
        self.assertEqual(self.backups('venv-backups'), [])
        self.assert_application_state_unchanged()

    def test_running_interpreter_cannot_be_moved_by_package_repair(self):
        self.python_library.unlink()
        with patch.object(deps.sys, 'executable', str(self.project.python)):
            with self.assertRaises(deps.VirtualEnvironmentRepairError):
                self.install(repair_packages=True)
        self.assertEqual(self.project.python.read_bytes(), b'original interpreter')
        self.assertEqual(self.backups('venv-backups'), [])
        self.assert_application_state_unchanged()
