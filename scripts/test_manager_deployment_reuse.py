"""Deployment evidence belongs only to one locked preparation/start operation."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
import subprocess
import sys
import json
import io
import threading
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher import installation, production_build, runtime
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.model import LauncherError
from scripts.launcher.installation_state import private_directory
from scripts.launcher_test_support import create_project
from scripts.manager import operations


class DeploymentReuseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        source = private_directory(self.root / 'home/r' / ('a' * 12), root=self.root / 'home')
        self.project = create_project(source)
        self.certificate, self.key = self.root / 'cert.pem', self.root / 'key.pem'
        self.certificate.touch()
        self.key.touch()
        self.profile = profiles.provision_profile(self.project, 'prod', self.root / 'home',
            host='192.0.2.10', tls_cert_file=self.certificate, tls_key_file=self.key)

    def start(self, **changes):
        with ExitStack() as stack:
            for name in ('require_windows_production', 'ensure_virtual_environment', 'require_production_host',
                         'require_port', 'require_external_file', 'validate_tls_identity',
                         'start_production_backend', 'supervise'):
                stack.enter_context(patch.object(runtime, name))
            stack.enter_context(patch.object(runtime, 'start_job_workers', return_value=[]))
            commands = stack.enter_context(patch.object(runtime, 'django'))
            stack.enter_context(patch.object(runtime, 'run_script'))
            options = dict(host=self.profile['host'], port=self.profile['backend_port'],
                env_file=Path(self.profile['env_file']), certificate_file=self.certificate,
                private_key_file=self.key, exclude_doors=False, migrate=False)
            runtime.prod(self.project, **{**options, **changes})
        return [call.args[1] for call in commands.call_args_list]

    def prepare(self, *, fail=False):
        result = subprocess.CompletedProcess([], int(fail), '', '')
        with patch.object(installation, 'capture', return_value=result):
            installation._deployment_checks(self.project, self.profile, {})

    def test_immediate_start_reuses_successful_deployment_only_once(self):
        with production_build.deployment_checks_scope():
            self.prepare()
            self.assertEqual(self.start(), [['migrate', '--check']])
            self.assertIn(['collectstatic', '--clear', '--noinput'], self.start())

    def test_next_operation_runs_every_deployment_gate(self):
        with production_build.deployment_checks_scope():
            self.prepare()
        with production_build.deployment_checks_scope():
            commands = self.start()
        self.assertEqual(commands, [['check', '--deploy'], ['migrate', '--check'],
                                   ['collectstatic', '--clear', '--noinput'], ['verify_frontend_artifact']])

    def test_changed_environment_cannot_reuse_preparation(self):
        with production_build.deployment_checks_scope():
            self.prepare()
            with Path(self.profile['env_file']).open('a', encoding='utf-8') as stream:
                stream.write('EXTRA_SETTING=changed\n')
            self.assertIn(['check', '--deploy'], self.start())

    def test_failed_deployment_does_not_authorize_start(self):
        with production_build.deployment_checks_scope():
            with self.assertRaises(LauncherError):
                self.prepare(fail=True)
            self.assertIn(['collectstatic', '--clear', '--noinput'], self.start())

    def test_failed_operation_does_not_leave_evidence(self):
        with self.assertRaises(RuntimeError):
            with production_build.deployment_checks_scope():
                self.prepare()
                raise RuntimeError('interrupted preparation')
        self.assertIn(['verify_frontend_artifact'], self.start())

    def test_other_source_cannot_reuse_preparation(self):
        source = self.root / 'other-source'
        source.mkdir()
        with production_build.deployment_checks_scope():
            self.prepare()
            self.project = create_project(source)
            self.assertIn(['collectstatic', '--clear', '--noinput'], self.start())

    def test_manager_scopes_preparation_and_immediate_start_together(self):
        args = operations.arguments({'action': 'provision', 'profile': 'prod'})
        args.progress = lambda _: None
        commands = []
        with patch.object(installation, 'provision', side_effect=lambda *_: self.prepare() or []), \
             patch.object(installation, 'start_profile', side_effect=lambda *_, **__: commands.extend(self.start())):
            operations._run_lifecycle(self.project, 'provision', args, lambda _: None)
        self.assertEqual(commands, [['migrate', '--check']])
        self.assertIn(['collectstatic', '--clear', '--noinput'], self.start())

    def test_production_commands_have_finite_timeouts(self):
        with patch.object(runtime, 'django') as django:
            # Preserve the real production flow while observing its command boundary.
            with ExitStack() as stack:
                for name in ('require_windows_production', 'ensure_virtual_environment', 'require_production_host',
                             'require_port', 'require_external_file', 'validate_tls_identity',
                             'start_production_backend', 'supervise'):
                    stack.enter_context(patch.object(runtime, name))
                stack.enter_context(patch.object(runtime, 'start_job_workers', return_value=[]))
                runtime.prod(self.project, host=self.profile['host'], port=self.profile['backend_port'],
                    env_file=Path(self.profile['env_file']), certificate_file=self.certificate,
                    private_key_file=self.key, exclude_doors=False, migrate=False)
        self.assertEqual(len(django.call_args_list), 4)
        self.assertTrue(all(0 < call.kwargs.get('timeout', float('inf')) < float('inf')
                            for call in django.call_args_list))

    def test_command_timeout_interrupts_a_stalled_child(self):
        from scripts.launcher.process import run
        with self.assertRaises(subprocess.TimeoutExpired):
            run([sys.executable, '-c', 'import time; time.sleep(30)'], self.root,
                capture=True, timeout=0.1)

    def test_django_forwards_command_timeout(self):
        from scripts.launcher.quality import django
        with patch('scripts.launcher.quality.run') as command:
            django(self.project, ['check', '--deploy'], timeout=180)
        self.assertEqual(command.call_args.kwargs['timeout'], 180)

    def test_mutating_start_discards_previous_deployment_proof(self):
        for changes in ({'migrate': True}, {'build_frontend': True}):
            with self.subTest(changes=changes), production_build.deployment_checks_scope():
                self.prepare()
                self.assertIn(['collectstatic', '--clear', '--noinput'], self.start(**changes))
                self.assertIn(['collectstatic', '--clear', '--noinput'], self.start())

    def test_manager_timeout_report_withholds_command_and_output(self):
        events = []
        error = subprocess.TimeoutExpired(['private-command-marker'], 180,
                                          output='private-output-marker', stderr='private-error-marker')
        with patch.object(operations, '_dispatch', side_effect=error):
            operations.execute({'action': 'start'}, events.append, lambda: None, threading.Event())
        failure = next(event for event in events if event['type'] == 'error')
        self.assertEqual(failure['code'], 'operation_timeout')
        self.assertNotIn('private-', json.dumps(events))

    def test_cli_timeout_returns_a_sanitized_failure(self):
        from scripts.launcher import cli
        output = io.StringIO()
        with patch.object(cli, 'discover_project', return_value=self.project), \
             patch.object(cli, 'dispatch', side_effect=subprocess.TimeoutExpired(['private-command-marker'], 180)), \
             redirect_stderr(output), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['check']), 1)
        self.assertIn('süre', output.getvalue())
        self.assertNotIn('private-', output.getvalue())

    def test_frontend_build_forwards_a_finite_timeout(self):
        from scripts.launcher.quality import run_script
        self.project.package_json.write_text('{"scripts":{"build":"vite build"}}')
        with patch('scripts.launcher.quality.required_tool', return_value='npm'), \
             patch('scripts.launcher.quality.run') as command:
            run_script(self.project, 'build', timeout=1800)
        self.assertEqual(command.call_args.kwargs['timeout'], 1800)
