"""TLS gates must precede profile publication and schema writes."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from scripts.launcher import installation
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project
from scripts.manager.operations import arguments


class ProvisionPreflightTests(unittest.TestCase):
    def test_bad_tls_stops_before_any_runtime_or_profile_write(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            (root / 'source').mkdir()
            project = create_project(root / 'source')
            home = root / 'private'
            args = arguments({'action': 'provision', 'profile': 'prod', 'host': '192.0.2.1',
                'tls_cert_file': str(root / 'missing.pem'), 'tls_key_file': str(root / 'missing.key')})
            stack.enter_context(patch.object(installation, 'require_windows'))
            stack.enter_context(patch.object(installation, 'installation_home', return_value=home))
            ensure = stack.enter_context(patch.object(installation, 'ensure_toolchain'))
            profile = stack.enter_context(patch.object(installation, 'provision_profile'))
            with self.assertRaises(LauncherError):
                installation.provision(project, args)
            ensure.assert_not_called()
            profile.assert_not_called()

    def test_full_tls_failure_never_creates_profile_or_schema(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            (root / 'source').mkdir()
            project = create_project(root / 'source')
            home = root / 'private'
            args = arguments({'action': 'provision', 'profile': 'prod', 'host': '192.0.2.1',
                'tls_cert_file': str(root / 'cert.pem'), 'tls_key_file': str(root / 'key.pem')})
            for name in ('cert.pem', 'key.pem'):
                (root / name).write_text('fixture')
            stack.enter_context(patch.object(installation, 'require_windows'))
            stack.enter_context(patch.object(installation, 'installation_home', return_value=home))
            stack.enter_context(patch('ssl.SSLContext.load_cert_chain'))
            stack.enter_context(patch('scripts.launcher.runtime_selection.tool_choices', return_value={}))
            stack.enter_context(patch.object(installation, 'ensure_toolchain', return_value={'AWCENTER_MANAGED_PYTHON': '/python'}))
            deps = stack.enter_context(patch.object(installation, 'install_dependencies'))
            stack.enter_context(patch.object(installation.runtime, 'validate_tls_identity', side_effect=LauncherError('TLS SAN')))
            profile = stack.enter_context(patch.object(installation, 'provision_profile'))
            schema = stack.enter_context(patch.object(installation, '_initialize_schema'))
            with self.assertRaisesRegex(LauncherError, 'TLS SAN'):
                installation.provision(project, args)
            deps.assert_called_once()
            profile.assert_not_called()
            schema.assert_not_called()

    def test_saved_tools_are_not_silently_replaced_by_discovery(self):
        from scripts.launcher.runtime_selection import tool_choices
        args = arguments({'action': 'provision'})
        with patch('scripts.launcher.system_python.discover_python') as python, \
             patch('scripts.launcher.system_node.discover_node') as node:
            choices = tool_choices(args, {'python_executable': '/saved/python', 'node_executable': '/saved/node'})
        self.assertEqual(choices, {'python_executable': Path('/saved/python'), 'node_executable': Path('/saved/node')})
        python.assert_not_called()
        node.assert_not_called()
