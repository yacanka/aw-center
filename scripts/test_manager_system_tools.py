"""System tool selection, managed fallback and prepared-profile persistence."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation, installation_profiles, toolchain
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher.process import OperationCancelled
from scripts.launcher.system_python import SystemPythonError
from scripts.manager import operations
from scripts.launcher_test_support import create_project


class ManagerSystemToolsTests(unittest.TestCase):
    def test_missing_automatic_python_selects_managed_download_once(self):
        args = operations.arguments({'action': 'provision'})
        with patch('scripts.launcher.system_python.discover_python',
                   side_effect=SystemPythonError('not_found')) as discover:
            self.assertEqual(operations._python_choice(args), {})
            self.assertEqual(operations._python_choice(args), {})
        self.assertTrue(args.install_python)
        self.assertEqual(discover.call_count, 1)

    def test_explicit_python_error_does_not_download_a_different_interpreter(self):
        args = operations.arguments({'action': 'provision', 'python_command': '/missing/python'})
        with patch('scripts.launcher.system_python.discover_python',
                   side_effect=SystemPythonError('path_missing')):
            with self.assertRaises(SystemPythonError):
                operations._python_choice(args)
        self.assertFalse(args.install_python)

    def test_python_cancellation_never_selects_download(self):
        args = operations.arguments({'action': 'provision'})
        with patch('scripts.launcher.system_python.discover_python', side_effect=OperationCancelled()):
            with self.assertRaises(OperationCancelled):
                operations._python_choice(args)
        self.assertFalse(args.install_python)

    def test_node_command_reaches_bundle_and_provision_arguments_only(self):
        for action in ('bundle', 'provision', 'start', 'doctor'):
            args = operations.arguments({'action': action, 'node_command': 'C:/Node/node.exe'})
            self.assertEqual(args.node_command, 'C:/Node/node.exe' if action in {'bundle', 'provision'} else None)

    def test_missing_automatic_node_falls_back_only_once(self):
        from scripts.launcher.system_node import SystemNodeError
        args = operations.arguments({'action': 'provision'})
        with patch('scripts.launcher.system_node.discover_node', side_effect=SystemNodeError('not_found')) as discover:
            self.assertEqual(operations._node_choice(args), {})
            self.assertEqual(operations._node_choice(args), {})
        self.assertEqual(discover.call_count, 1)

    def test_explicit_node_error_and_cancellation_never_select_download(self):
        from scripts.launcher.system_node import SystemNodeError
        for failure in (SystemNodeError('architecture'), OperationCancelled()):
            with self.subTest(failure=type(failure).__name__):
                args = operations.arguments({'action': 'provision', 'node_command': 'node'})
                with patch('scripts.launcher.system_node.discover_node', side_effect=failure):
                    with self.assertRaises(type(failure)):
                        operations._node_choice(args)
                self.assertFalse(getattr(args, '_node_checked', False))

    def test_manager_preserves_safe_node_error_in_report(self):
        from scripts.launcher.system_node import SystemNodeError
        import threading
        events = []
        with patch.object(operations, '_dispatch', side_effect=SystemNodeError('architecture')):
            operations.execute({'action': 'provision'}, events.append, lambda: None, threading.Event())
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'system_node_architecture')
        self.assertIn('x64', error['remedy'])

    def test_bundle_uses_selected_npm_cli_without_a_path_shim(self):
        from scripts.launcher.installation_bundle import _npm_argv
        import os
        with tempfile.TemporaryDirectory() as temporary:
            cli = Path(temporary).resolve() / 'npm-cli.js'
            cli.write_text('// npm fixture', encoding='utf-8')
            node = str(Path(sys.executable).resolve())
            with patch.dict(os.environ, {'AWCENTER_MANAGED_NODE': node, 'AWCENTER_MANAGED_NPM_CLI': str(cli)}), \
                 patch('scripts.launcher.process.required_tool', side_effect=installation.LauncherError('npm is not on PATH')):
                self.assertEqual(_npm_argv(), [node, str(cli)])

    def test_manager_bundle_uses_complete_isolated_preparer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            args = operations.arguments({'action': 'bundle', 'output': str(root / 'output'),
                                         'manager_distribution': str(root / 'manager')})
            args.progress = lambda _: None
            with patch('scripts.manager.distribution.prepare_full_manager') as prepare, \
                 patch('scripts.launcher.system_python.discover_python') as discover, \
                 patch.object(toolchain, 'ensure_toolchain') as live_tools:
                operations._bundle(project, args, lambda _: None)
            self.assertEqual(prepare.call_args.args[3], root / 'manager')
            self.assertNotIn('external_runtimes', prepare.call_args.kwargs)
            discover.assert_not_called()
            live_tools.assert_not_called()

    def test_bundle_requires_matching_manager_distribution(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            args = operations.arguments({'action': 'bundle', 'output': '/unused-output'})
            args.progress = lambda _: None
            with patch('scripts.manager.distribution.prepare_full_manager') as prepare:
                with self.assertRaisesRegex(installation.LauncherError, 'Windows Manager'):
                    operations._bundle(project, args, lambda _: None)
            prepare.assert_not_called()

    def test_node_pointer_is_profile_scoped_and_keeps_private_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            project = create_project(source)
            profile = installation_profiles.provision_profile(project, 'dev', root / 'private')
            original = Path(profile['env_file']).read_bytes()
            node = root / 'operator-node.exe'
            updated = installation_profiles.update_node_runtime(project, profile, node)
            self.assertEqual(installation_profiles.load_profile(project, 'dev', root / 'private')['node_executable'], str(node))
            self.assertEqual(Path(updated['env_file']).read_bytes(), original)
            restored = installation_profiles.update_node_runtime(project, updated, None)
            self.assertNotIn('node_executable', restored)
            self.assertEqual(Path(restored['env_file']).read_bytes(), original)

    def test_invalid_saved_node_pointer_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            project = create_project(source)
            profile = installation_profiles.provision_profile(project, 'dev', root / 'private')
            with self.assertRaises(installation.LauncherError):
                installation_profiles.update_node_runtime(project, profile, Path('relative-node.exe'))

    def test_node_selection_survives_provision_and_prepared_restart(self):
        python = Path(sys.executable).resolve()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as mocks:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            project = create_project(source)
            home = root / 'private'
            profile = installation_profiles.provision_profile(project, 'dev', home)
            node = root / 'operator-node.exe'
            original = Path(profile['env_file']).read_bytes()
            args = operations.arguments({'action': 'provision'})
            args.python_executable, args.node_executable = python, node
            mocks.enter_context(patch.object(installation, 'require_windows'))
            mocks.enter_context(patch.object(installation, 'installation_home', return_value=home))
            mocks.enter_context(patch.object(installation_profiles, 'installation_home', return_value=home))
            mocks.enter_context(patch.object(installation, 'source_settings', return_value=SourceSettings()))
            ensure = mocks.enter_context(patch.object(installation, 'ensure_toolchain', return_value={
                'AWCENTER_MANAGED_PYTHON': str(python), 'AWCENTER_MANAGED_NODE': str(node)}))
            mocks.enter_context(patch.object(installation, 'install_dependencies'))
            mocks.enter_context(patch.object(installation, '_initialize_schema'))
            mocks.enter_context(patch.object(installation, '_initial_admin'))
            mocks.enter_context(patch.object(installation, '_core_checks', return_value=[]))
            mocks.enter_context(patch('scripts.launcher.installation_features.install_features', return_value=[]))
            installation.provision(project, args)
            self.assertEqual(ensure.call_args.kwargs['node_executable'], node)
            self.assertEqual(installation_profiles.load_profile(project, 'dev', home)['node_executable'], str(node))
            inspect = mocks.enter_context(patch.object(installation, 'inspect_toolchain', return_value=[]))
            tools = mocks.enter_context(patch.object(toolchain, 'toolchain_environment', return_value={}))
            mocks.enter_context(patch('scripts.launcher.installation_features.feature_environment', return_value={}))
            mocks.enter_context(patch.object(installation, '_django'))
            mocks.enter_context(patch.object(installation.runtime, 'dev'))
            installation.start_profile(project, 'dev')
            self.assertEqual(inspect.call_args.kwargs['node_executable'], node)
            self.assertEqual(tools.call_args.kwargs['node_executable'], node)
            self.assertEqual(Path(profile['env_file']).read_bytes(), original)
