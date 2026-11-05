"""Integration contracts for the Windows installation helper."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.launcher.model import LauncherError
from scripts.launcher.parser import build_parser
from scripts.launcher_test_support import create_project


class InstallationParserTests(unittest.TestCase):
    def test_managed_commands_keep_existing_cli_available(self):
        parser = build_parser()
        for command in ("provision", "doctor", "start"):
            with self.subTest(command=command):
                args = parser.parse_args([command, "--profile", "prod"])
                self.assertEqual(args.profile, "prod")
        args = parser.parse_args(["prepare-install-bundle", "--output", "bundle"])
        self.assertEqual(args.output, Path("bundle"))
        self.assertEqual(parser.parse_args(["wizard"]).command, "wizard")
        self.assertFalse(parser.parse_args(["dev"]).migrate)


class ManagedReadinessTests(unittest.TestCase):
    def test_dev_checks_live_and_vite_without_production_artifact(self):
        from scripts.launcher.installation_readiness import wait_until_ready

        with tempfile.TemporaryDirectory() as temporary:
            markers = Path(temporary)
            for name in ("job", "notification", "cleanup"):
                (markers / name).write_text("worker-1", encoding="utf-8")
            process = mock.Mock()
            process.poll.return_value = None
            profile = {"name": "dev", "host": "127.0.0.1", "backend_port": 8000,
                       "frontend_port": 5173}
            with mock.patch("scripts.launcher.installation_readiness.probe_http", return_value=True) as probe:
                wait_until_ready([process], profile, markers, worker_check=lambda: True, timeout=1)
            self.assertEqual([call.args[0] for call in probe.call_args_list], [
                "http://127.0.0.1:8000/health/live/", "http://127.0.0.1:5173/app/",
            ])

    def test_timeout_identifies_only_components_that_are_not_ready(self):
        from scripts.launcher.installation_readiness import wait_until_ready
        from scripts.manager.operations import _failure_reason
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ('job', 'notification', 'cleanup'):
                (directory / name).touch()
            process = mock.Mock()
            process.poll.return_value = None
            profile = {'name': 'dev', 'host': '127.0.0.1', 'backend_port': 8000,
                       'frontend_port': 5173}
            with mock.patch('scripts.launcher.installation_readiness.probe_http', return_value=True):
                with self.assertRaises(LauncherError) as caught:
                    wait_until_ready([process], profile, directory, worker_check=lambda: False, timeout=0)
            code, reason = _failure_reason(caught.exception)
            self.assertEqual(code, 'startup_not_ready')
            self.assertIn('worker heartbeat', reason)
            self.assertNotIn('frontend', reason)

    def test_worker_health_reads_current_receipt_without_booting_django(self):
        from scripts.launcher.installation import _worker_ready
        import time
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'job').write_text('worker-current')
            now = time.time()
            receipt = {'worker_id': 'worker-current', 'checked_at': now, 'valid_until': now + 10}
            (directory / 'worker-health.json').write_text(json.dumps(receipt))
            with mock.patch('scripts.launcher.installation.controlled_run',
                            side_effect=AssertionError('health check rebooted Django')):
                self.assertTrue(_worker_ready(create_project(directory), directory))
                for changes in ({'worker_id': 'another-worker'}, {'checked_at': now - 10},
                                {'valid_until': now - 1}, {'valid_until': float('nan')}, {'valid_until': 10 ** 400}):
                    (directory / 'worker-health.json').write_text(json.dumps({**receipt, **changes}))
                    self.assertFalse(_worker_ready(None, directory))

    def test_slow_health_monitor_can_finish_without_being_restarted(self):
        import sys
        import threading
        from scripts.launcher.installation import _worker_ready
        from scripts.launcher.installation_readiness import wait_until_ready
        from scripts.launcher.process import operation_control, start, starting_processes, terminate
        with tempfile.TemporaryDirectory() as temporary, operation_control(threading.Event()):
            directory = Path(temporary)
            for name in ('job', 'notification', 'cleanup'):
                (directory / name).write_text('owned-worker')
            program = ("import json,sys,time; from pathlib import Path; time.sleep(6); "
                       "now=time.time(); Path(sys.argv[1]).write_text(json.dumps({"
                       "'worker_id':'owned-worker','checked_at':now,'valid_until':now+10})); time.sleep(30)")
            project = create_project(directory)
            with starting_processes() as children:
                children.append(start([sys.executable, '-c', program, directory / 'worker-health.json'], directory))
                try:
                    with mock.patch('scripts.launcher.installation_readiness.probe_http', return_value=True):
                        wait_until_ready(children, {'name': 'dev', 'host': '127.0.0.1',
                            'backend_port': 8000, 'frontend_port': 5173}, directory,
                            worker_check=lambda: _worker_ready(project, directory), timeout=15)
                    self.assertIsNone(children[0].poll())
                finally:
                    terminate(children)

    def test_exited_owned_process_fails_startup(self):
        from scripts.launcher.installation_readiness import wait_until_ready

        process = mock.Mock()
        process.poll.return_value = 3
        with self.assertRaises(LauncherError):
            wait_until_ready([process], {"name": "dev"}, Path("missing"), timeout=0.1)

    def test_missing_worker_identity_cannot_be_ready(self):
        from scripts.launcher.installation_readiness import wait_until_ready

        process = mock.Mock()
        process.poll.return_value = None
        profile = {"name": "dev", "host": "127.0.0.1", "backend_port": 8000,
                   "frontend_port": 5173}
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch("scripts.launcher.installation_readiness.probe_http", return_value=True):
                with self.assertRaisesRegex(LauncherError, "hazır"):
                    wait_until_ready([process], profile, Path(temporary), timeout=0.01)


class ManagedWorkflowTests(unittest.TestCase):
    def test_deployment_checks_keep_real_notification_transport(self):
        from scripts.launcher.installation import _django

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))

            def capture(command, project, overrides):
                return subprocess.CompletedProcess(command, int(overrides.get("AWCENTER_MAIL_TRANSPORT") == "django"), "", "")

            with mock.patch("scripts.launcher.installation.profile_environment", return_value={"AWCENTER_MAIL_TRANSPORT": "django"}), \
                 mock.patch("scripts.launcher.installation.capture", side_effect=capture):
                with self.assertRaises(LauncherError):
                    _django(project, {}, ["check", "--deploy", "--fail-level", "ERROR"], {})

    def test_non_notification_roles_disable_smtp_even_with_shared_credentials(self):
        from scripts.launcher.job_worker import start_job_workers
        from scripts.test_launcher_jobs import add_auxiliary_worker_commands, add_worker_command

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            add_worker_command(project)
            add_auxiliary_worker_commands(project)
            values = {"AWCENTER_MAIL_TRANSPORT": "django", "EMAIL_HOST_USER": "fixture-smtp-user",
                      "EMAIL_HOST_PASSWORD": "fixture-smtp-password", "AWCENTER_PASSWORD": "fixture-shared"}
            with mock.patch("scripts.launcher.job_worker.start", return_value=mock.Mock()) as start:
                start_job_workers(project, values, protect_credentials=True)
            for call in start.call_args_list:
                child = call.kwargs["extra_env"]
                if "run_compdoc_notification_worker" in call.args[0]:
                    self.assertEqual(child["AWCENTER_MAIL_TRANSPORT"], "django")
                    self.assertEqual(child["EMAIL_HOST_PASSWORD"], "fixture-smtp-password")
                else:
                    self.assertEqual(child["AWCENTER_MAIL_TRANSPORT"], "disabled")
                    self.assertEqual(child["EMAIL_HOST_PASSWORD"], "")
                    self.assertEqual(child["EMAIL_HOST_USER"], "")

    def test_frontend_does_not_inherit_backend_profile_or_credentials(self):
        from scripts.launcher.runtime import start_frontend
        from scripts.launcher.process import environment

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            inherited = {"SECRET_KEY": "fixture-sensitive-marker", "EMAIL_HOST_PASSWORD": "fixture-mail-marker",
                         "AWCENTER_ENV_FILE": "fixture-private-pointer", "JIRA_SESSION_ENCRYPTION_KEY": "fixture-jira-marker"}
            with mock.patch.dict(os.environ, inherited), \
                 mock.patch("scripts.launcher.runtime.required_tool", return_value="npm"), \
                 mock.patch("scripts.launcher.runtime.start", side_effect=lambda *_, **kw: environment(kw["extra_env"])):
                child = start_frontend(project, "127.0.0.1", 8000, 5173, protect_credentials=True)
                for key in inherited:
                    self.assertNotIn(key, child)
                    self.assertEqual(os.environ[key], inherited[key])
                self.assertEqual(child["VITE_API_URL"], "http://127.0.0.1:8000")

    def test_existing_database_without_schema_requires_explicit_migration(self):
        from scripts.launcher.installation import _initialize_schema

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            database = project.backend / "db.sqlite3"
            database.touch()
            with mock.patch("scripts.launcher.installation.backend_inspection", return_value={"schema": "missing"}), \
                 mock.patch("scripts.launcher.installation.read_profile_environment", return_value={"DATABASE_URL": "sqlite:///" + str(database)}), \
                 mock.patch("scripts.launcher.installation._django") as django:
                with self.assertRaisesRegex(LauncherError, "--migrate"):
                    _initialize_schema(project, {}, SimpleNamespace(migrate=False), {})
            django.assert_not_called()

    def test_doctor_without_profile_does_not_provision(self):
        from scripts.launcher.installation import doctor

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_project(root)
            home = root / "not-created"
            with mock.patch("scripts.launcher.installation.installation_home", return_value=home):
                checks = doctor(project, "dev")
            self.assertFalse(home.exists())
            self.assertTrue(any(check["status"] == "blocked" for check in checks))

    def test_normal_start_never_migrates_and_keeps_supervision(self):
        from scripts.launcher.installation import start_profile

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary).resolve())
            profile = {"name": "dev", "host": "127.0.0.1", "backend_port": 8000,
                       "frontend_port": 5173, "exclude_doors": True,
                       "installation_home": str(project.root / "private"),
                       "env_file": str(project.root / "private/config/dev.env")}
            with mock.patch("scripts.launcher.installation.require_windows"), \
                 mock.patch("scripts.launcher.installation.load_profile", return_value=profile), \
                 mock.patch("scripts.launcher.installation.profile_environment", return_value={}), \
                 mock.patch("scripts.launcher.installation.inspect_toolchain", return_value=[]), \
                 mock.patch("scripts.launcher.toolchain.toolchain_environment", return_value={}), \
                 mock.patch("scripts.launcher.installation_features.feature_environment", return_value={}), \
                 mock.patch("scripts.launcher.installation._django"), \
                 mock.patch("scripts.launcher.installation.runtime.dev") as dev, \
                 mock.patch("scripts.launcher.installation.runtime_session") as session:
                session.return_value.__enter__.return_value = project.root
                start_profile(project, "dev")
            self.assertFalse(dev.call_args.kwargs["migrate"])
            self.assertTrue(callable(dev.call_args.kwargs["ready"]))


if __name__ == "__main__":
    unittest.main()
