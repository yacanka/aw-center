"""Pip failures expose actionable evidence, never private tool output."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import installation_bundle as bundle
from scripts.launcher import installation_dependencies as deps
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher_test_support import create_project
from scripts.manager import worker


class PackageDiagnosticTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = create_project(self.root)
        self.project.requirements.write_text(
            'httpx2==2.16.0\nhttpcore2==2.16.0\nhuggingface-hub==2.2.0\n'
            'httpx2-jsfetch==1.0 ; sys_platform == "emscripten"\n', encoding='utf-8')

    def fail_acquisition(self, output, *, operation='install'):
        events = []
        settings = SourceSettings(mode='corporate', python_index_url='https://selected.invalid/simple',
                                  progress=events.append)
        result = subprocess.CompletedProcess(['private-command'], 1, '', output)
        if operation == 'install':
            with patch.object(deps, 'capture', return_value=result):
                with self.assertRaises(deps.PackageCommandError) as caught:
                    deps._python_packages(self.project, settings, {}, self.root)
        else:
            with patch.object(bundle, '_capture', return_value=result):
                with self.assertRaises(deps.PackageCommandError) as caught:
                    bundle._acquire_wheels(self.project, self.root / 'wheels', settings, {})
        return caught.exception, events

    def test_missing_distribution_names_the_locked_package_in_install_and_bundle(self):
        for operation in ('install', 'bundle'):
            with self.subTest(operation=operation):
                error, events = self.fail_acquisition(
                    'Ignoring httpx2-jsfetch: markers do not match your environment\n'
                    'ERROR: Could not find a version that satisfies the requirement httpx2==2.16.0 (from versions: none)\n'
                    'ERROR: No matching distribution found for httpx2==2.16.0', operation=operation)
                self.assertEqual(error.code, 'package_distribution_not_found')
                self.assertIn('No matching distribution found', str(error))
                self.assertIn('httpx2==2.16.0', str(error))
                self.assertNotIn('httpx2-jsfetch', str(error))
                self.assertIn('depo', error.remedy)
                self.assertIn('Python', error.remedy)
                self.assertNotIn('private-command', str(error) + json.dumps(events))

    def test_resolution_conflict_keeps_only_locked_package_names(self):
        error, _ = self.fail_acquisition(
            'ERROR: Cannot install httpx2==2.16.0 and huggingface-hub==2.2.0 because these package versions have conflicting dependencies.\n'
            'The conflict is caused by:\n'
            '    The user requested httpx2==2.16.0\n'
            '    huggingface-hub 2.2.0 depends on httpx2>=2\n'
            'ERROR: ResolutionImpossible: for help visit https://private.invalid/?token=secret-fixture')
        self.assertEqual(error.code, 'package_dependency_conflict')
        self.assertIn('ResolutionImpossible', str(error))
        self.assertIn('httpx2==2.16.0', str(error))
        self.assertIn('huggingface-hub==2.2.0', str(error))
        self.assertNotIn('private.invalid', str(error))
        self.assertNotIn('secret-fixture', str(error))

    def test_python_version_mismatch_is_distinct_from_missing_distribution(self):
        error, _ = self.fail_acquisition(
            "ERROR: Package 'httpx2' requires a different Python: 3.10.14 not in '>=3.11'")
        self.assertEqual(error.code, 'package_python_incompatible')
        self.assertIn('requires a different Python', str(error))
        self.assertIn('httpx2==2.16.0', str(error))
        self.assertIn('3.11', error.remedy)

    def test_wheel_build_failure_names_the_package_but_not_build_output(self):
        error, _ = self.fail_acquisition(
            'Building wheel for httpx2 (pyproject.toml): finished with status \'error\'\n'
            'ERROR: Failed building wheel for httpx2\n'
            'secret-fixture C:\\Users\\private-user\\build HTTP_PROXY=https://secret@private.invalid')
        self.assertEqual(error.code, 'package_wheel_build_failed')
        self.assertIn('Failed building wheel', str(error))
        self.assertIn('httpx2==2.16.0', str(error))
        for private in ('secret', 'private-user', 'private.invalid'):
            self.assertNotIn(private, str(error) + error.remedy)

    def test_metadata_and_build_subprocess_failures_have_distinct_evidence(self):
        cases = (('error: metadata-generation-failed', 'package_metadata_failed'),
                 ('error: subprocess-exited-with-error', 'package_build_subprocess_failed'))
        for number, (output, expected) in enumerate(cases):
            # Use the error formatter directly; acquisition staging is irrelevant here.
            with self.subTest(output=output):
                error = deps.PackageCommandError(subprocess.CompletedProcess([], 1, '', output))
                self.assertEqual(error.code, expected)
                self.assertIn(output.removeprefix('error: '), str(error))

    def test_pip_check_reports_missing_and_incompatible_locked_dependencies(self):
        for output, code in (
            ('httpx2 2.16.0 requires httpcore2, which is not installed.', 'package_dependency_missing'),
            ('httpx2 2.16.0 has requirement httpcore2==2.16.0, but you have httpcore2 2.15.0.', 'package_dependency_conflict'),
        ):
            with self.subTest(output=output):
                # Reach the real validation step after successful acquisition/install.
                result = subprocess.CompletedProcess([], 1, output, '')
                wheelhouse = self.root / 'offline'
                wheelhouse.mkdir(exist_ok=True)
                with patch.object(deps, '_offline_dependencies', return_value=wheelhouse), \
                     patch.object(deps, 'capture', side_effect=[subprocess.CompletedProcess([], 0, '', ''), result]):
                    with self.assertRaises(deps.PackageCommandError) as caught:
                        deps._python_packages(self.project, SourceSettings(), {}, self.root)
                self.assertEqual(caught.exception.code, code)
                self.assertIn('httpx2==2.16.0', str(caught.exception))
                self.assertIn('httpcore2==2.16.0', str(caught.exception))

    def test_package_looking_secrets_and_arbitrary_diagnostics_are_not_reflected(self):
        error, events = self.fail_acquisition(
            'ERROR: No matching distribution found for private-token-fixture==987\n'
            'ERROR: No matching distribution found for httpx2==secret-version-fixture\n'
            'ERROR: No matching distribution found for https://user:password-fixture@private.invalid/pkg\n'
            'Authorization: Bearer bearer-fixture\n'
            'PIP_INDEX_URL=https://private.invalid/simple?token=query-fixture\n'
            'C:\\Users\\person-fixture\\requirements.txt\n'
            'ERROR: No matching distribution found for httpcore2==2.16.0')
        rendered = str(error) + error.remedy + json.dumps(events)
        for private in ('private-token-fixture', 'secret-version-fixture', 'password-fixture',
                        'private.invalid', 'bearer-fixture', 'query-fixture', 'person-fixture'):
            self.assertNotIn(private, rendered)
        self.assertIn('httpcore2==2.16.0', rendered)

    def test_tls_failure_wins_over_secondary_resolution_error_and_keeps_no_fallback(self):
        output = ('CERTIFICATE_VERIFY_FAILED https://private.invalid/secret-fixture\n'
                  'ERROR: No matching distribution found for httpx2==2.16.0')
        error, _ = self.fail_acquisition(output)
        self.assertEqual(error.code, 'package_tls_failed')
        self.assertFalse(deps.availability_failure(output, restricted=True))
        self.assertNotIn('private.invalid', str(error))
        self.assertNotIn('secret-fixture', str(error))

    def test_transport_fallback_and_source_cause_survive_secondary_resolution_error(self):
        output = ('ReadTimeoutError: private-fixture\n'
                  'ERROR: No matching distribution found for httpx2==2.16.0')
        self.assertTrue(deps.availability_failure(output, restricted=True))
        error, _ = self.fail_acquisition(output)
        self.assertEqual(error.code, 'package_source_timeout')
        self.assertNotIn('No matching distribution found', str(error))
        self.assertIn('httpx2==2.16.0', str(error))
        self.assertNotIn('private-fixture', str(error))

    def test_ignored_or_last_collected_package_is_not_falsely_blamed(self):
        error, _ = self.fail_acquisition(
            'Ignoring httpx2-jsfetch: markers do not match your environment\n'
            'Collecting httpx2==2.16.0\nUnexpected private-fixture tool failure')
        self.assertEqual(error.code, 'package_command_failed')
        for value in ('httpx2', 'private-fixture'):
            self.assertNotIn(value, str(error))

    def test_indented_pip_errors_are_recognized(self):
        error = deps.PackageCommandError(subprocess.CompletedProcess([], 1, '',
            '  error: metadata-generation-failed\n  private-fixture'))
        self.assertEqual(error.code, 'package_metadata_failed')
        self.assertNotIn('private-fixture', str(error))

    def test_resolution_and_metadata_failures_do_not_expand_source_fallback(self):
        for diagnostic in ('ERROR: ResolutionImpossible', 'error: metadata-generation-failed',
                           'Failed to build httpx2 httpcore2',
                           'ERROR: Cannot install httpx2==2.16.0 and httpcore2==2.16.0 because these package versions have conflicting dependencies.',
                           "ERROR: Package 'httpx2' requires a different Python: 3.10 not in '>=3.11'"):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(deps.availability_failure('ReadTimeoutError\n' + diagnostic, restricted=True))

    def test_pip_space_separated_failed_build_summary_includes_all_locked_subjects(self):
        error, _ = self.fail_acquisition('Failed to build httpx2 private-fixture httpcore2')
        self.assertEqual(error.code, 'package_wheel_build_failed')
        self.assertIn('httpx2==2.16.0', str(error))
        self.assertIn('httpcore2==2.16.0', str(error))
        self.assertNotIn('private-fixture', str(error))

    def test_normalized_package_names_are_matched_to_the_lock(self):
        error, _ = self.fail_acquisition('ERROR: Failed building wheel for HuggingFace_Hub')
        self.assertIn('huggingface-hub==2.2.0', str(error))

    def test_offline_bundle_validation_reports_the_failed_package(self):
        wheelhouse = self.root / 'offline'
        (wheelhouse / 'wheels').mkdir(parents=True)
        (wheelhouse / 'wheels' / 'fixture.whl').write_bytes(b'fixture')
        with patch.object(bundle, '_offline_source', return_value=wheelhouse), \
             patch.object(bundle, '_capture', return_value=subprocess.CompletedProcess([], 1, '',
                 'ERROR: No matching distribution found for httpx2==2.16.0')):
            with self.assertRaises(deps.PackageCommandError) as caught:
                bundle._acquire_wheels(self.project, self.root / 'output', SourceSettings(), {})
        self.assertIn('Python bağımlılık doğrulaması', str(caught.exception))
        self.assertIn('httpx2==2.16.0', str(caught.exception))

    def test_unreadable_or_url_only_lock_does_not_mask_error_or_disclose_data(self):
        for lock in (None, self.root / 'absent', self.project.requirements):
            self.project.requirements.write_text('httpx2 @ https://private.invalid/?token=private-fixture\n')
            with self.subTest(lock=lock):
                error = deps.PackageCommandError(subprocess.CompletedProcess([], 1, '',
                    'ERROR: No matching distribution found for httpx2'), requirements=lock)
                self.assertEqual(error.code, 'package_distribution_not_found')
                for private in ('httpx2', 'private.invalid', 'private-fixture'):
                    self.assertNotIn(private, str(error))

    def test_real_pip_missing_distribution_is_formatted_without_raw_output(self):
        command = [sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps',
                   '--wheel-dir', self.root / 'wheels', '-r', self.project.requirements]
        result = deps.capture(command, self.project)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No matching distribution found', result.stderr)
        with self.assertRaises(deps.PackageCommandError) as caught:
            deps._succeeded(result, 'Python paket edinimi', requirements=self.project.requirements)
        self.assertIn('httpx2==2.16.0', str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_manager_error_event_retains_the_safe_diagnostic(self):
        events = []
        def dispatch(action, args, emit):
            deps._python_packages(self.project, SourceSettings(mode='corporate',
                python_index_url='https://selected.invalid/simple', progress=args.progress), {}, self.root)
        with patch('scripts.manager.operations._dispatch', side_effect=dispatch), \
             patch.object(deps, 'capture', return_value=subprocess.CompletedProcess([], 1, '',
                 'ERROR: No matching distribution found for httpx2==2.16.0')):
            worker.execute({'action': 'provision'}, events.append, lambda: None, threading.Event())
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'package_distribution_not_found')
        self.assertIn('httpx2==2.16.0', error['message'])
        self.assertIn('No matching distribution found', error['message'])
        self.assertEqual(events[-1], {'type': 'done', 'ok': False})


if __name__ == '__main__':
    unittest.main()
