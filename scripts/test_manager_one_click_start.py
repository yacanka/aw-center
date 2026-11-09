"""Decision boundaries for opening configured and partly prepared profiles."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import installation, installation_profiles as profiles
from scripts.launcher_test_support import create_project
from scripts.manager import ensure, operations


class OneClickStartTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.home = root / 'home'
        source = root / 'source'
        source.mkdir()
        self.project = create_project(source)
        location = patch.object(profiles, 'installation_home', return_value=self.home)
        location.start()
        self.addCleanup(location.stop)

    def execute(self, **values):
        events = []
        request = {'action': 'ensure', 'source_root': str(self.project.root), **values}
        operations.execute(request, events.append, lambda: None, threading.Event())
        return events

    def test_first_prod_reports_all_missing_fields_before_source_staging(self):
        for supplied, missing, field in (
            ({}, ('IPv4', 'TLS sertifikası', 'TLS özel anahtarı'), 'host'),
            ({'host': '192.0.2.1', 'tls_cert_file': str(self.home / 'cert.pem')},
             ('TLS özel anahtarı',), 'tls_key_file'),
        ):
            with self.subTest(field=field), patch.object(operations, '_project_for') as stage:
                events = self.execute(profile='prod', **supplied)
                stage.assert_not_called()
                errors = [e for e in events if e['type'] == 'error']
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0]['field'], field)
                self.assertEqual(errors[0]['code'], 'production_settings_required')
                for label in missing:
                    self.assertIn(label, errors[0]['message'])
                self.assertNotIn('cert.pem', str(errors[0]))

    def test_orphan_environment_stops_before_staging_or_package_preparation(self):
        from scripts.launcher.installation_state import private_directory
        from scripts.launcher.installation_permissions import secure_path

        env = private_directory(self.home / 'config', root=self.home) / 'prod.env'
        env.write_bytes(b'preserved')
        secure_path(env)
        with patch.object(operations, '_project_for') as stage:
            events = self.execute(profile='prod')
        stage.assert_not_called()
        error = next(e for e in events if e['type'] == 'error')
        self.assertEqual(error['code'], 'profile_metadata_missing')
        self.assertEqual(env.read_bytes(), b'preserved')

    def test_updated_connection_uses_start_when_current_environment_is_ready(self):
        original = profiles.provision_profile(self.project, 'dev', self.home)
        ready = [{'status': 'ready'}]
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(installation, '_core_checks', return_value=ready), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=ready), \
             patch.object(installation, 'provision') as provision, patch.object(installation, 'start_profile') as start:
            events = self.execute(frontend_port='15173')
            self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
            provision.assert_not_called()
            start.assert_called_once()
        current = profiles.load_profile(self.project, 'dev', self.home)
        self.assertEqual(current['frontend_port'], 15173)
        self.assertEqual(current['source_root'], original['source_root'])

    def test_changed_connection_still_prepares_when_another_requirement_is_missing(self):
        profiles.provision_profile(self.project, 'dev', self.home)
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(installation, '_core_checks', return_value=[{'status': 'missing'}]), \
             patch('scripts.launcher.toolchain.inspect_toolchain', return_value=[]), \
             patch.object(installation, 'provision') as provision, patch.object(installation, 'start_profile') as start:
            events = self.execute(frontend_port='15173')
            self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
            provision.assert_called_once()
            start.assert_called_once()

    def test_new_lease_rechecks_the_branch_found_by_the_previous_lease(self):
        profiles.provision_profile(self.project, 'dev', self.home)
        def incomplete_under_lease(project, args, **options):
            return not options.get('before_lock', False)
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(ensure, 'needs_preparation', side_effect=incomplete_under_lease) as decision, \
             patch.object(installation, 'provision') as provision, patch.object(installation, 'start_profile'):
            events = self.execute()
        self.assertEqual(events[-1], {'type': 'done', 'ok': True}, events)
        self.assertEqual(provision.call_count, 1)
        self.assertEqual([call.kwargs.get('before_lock', False) for call in decision.call_args_list],
                         [True, False, False])

    def test_incomplete_production_build_remains_preparable_after_admin_was_created(self):
        state = {'schema': 'ready', 'admin_exists': True, 'frontend_build_ready': False}
        with patch.object(installation, 'inspect_profile', return_value=[]), \
             patch.object(installation, 'dependency_checks', return_value=[{'status': 'ready'}]), \
             patch.object(installation, 'backend_inspection', return_value=state):
            checks = installation._core_checks(self.project, {'name': 'prod'})
        self.assertIn(('frontend-build', 'missing'), [(row.get('name'), row['status']) for row in checks])

    def test_lease_change_does_not_consume_automatic_port_retries(self):
        from scripts.launcher.runtime import PortUnavailable
        from scripts.launcher.installation_connection import ConnectionError

        profiles.provision_profile(self.project, 'dev', self.home, port_modes={
            'frontend_port': 'automatic', 'backend_port': 'automatic'})
        args = operations.arguments({'action': 'ensure', 'source_root': str(self.project.root)})
        args.progress = lambda message: None
        args.source_root = str(self.project.root)
        clash = PortUnavailable('127.0.0.1', 5173)
        with patch.object(operations, '_project_for', return_value=self.project), \
             patch.object(ensure, 'needs_preparation', return_value=False), \
             patch.object(operations, '_dispatch', side_effect=[ensure.Replan('provision'), clash, clash, clash]) as run:
            with self.assertRaises(ConnectionError) as caught:
                ensure.run(args, lambda event: None)
        self.assertEqual(caught.exception.field, 'frontend_port')
        self.assertEqual(run.call_count, 4)

    def test_build_evidence_failure_gives_the_operator_its_specific_remedy(self):
        from scripts.launcher.production_build import FrontendBuildError

        problem = FrontendBuildError()
        with patch.object(operations, '_dispatch', side_effect=problem):
            events = self.execute(profile='prod')
        event = next(e for e in events if e['type'] == 'error')
        self.assertEqual((event['code'], event['remedy']), (problem.code, problem.remedy))
