"""Desktop validation defaults and launcher admission contracts."""
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.launcher.model import LauncherError
from scripts.manager import paths
from scripts.manager.view_model import FormError, ManagerTaskStates, normalize_values


class ValidationPolicyTests(unittest.TestCase):
    def policy(self, *args, **kwargs):
        helper = importlib.import_module('scripts.launcher.validation_policy')
        return helper.require_validation_policy(*args, **kwargs)

    def test_only_desktop_defaults_to_fast_validation(self):
        self.assertEqual(self.policy(), 'managed')
        self.assertEqual(normalize_values('start', {})['validation_policy'], 'developer')

    def test_unknown_policies_are_safe_structured_errors(self):
        for value in ('', None, False, [], 'Developer', 'unknown-token=secret'):
            with self.subTest(value=value), self.assertRaises(LauncherError) as caught:
                self.policy(value)
            self.assertEqual(caught.exception.code, 'invalid_validation_policy')
            self.assertEqual(caught.exception.field, 'validation_policy')
            self.assertNotIn('secret', str(caught.exception))

    def test_developer_accepts_both_profiles_and_source_selections(self):
        self.assertEqual(self.policy('developer'), 'developer')
        self.assertEqual(self.policy('developer', source_selection='explicit'), 'developer')
        self.assertEqual(self.policy('developer', source_selection='automatic'), 'developer')
        for selection in ('automatic', 'explicit'):
            with self.subTest(selection=selection):
                self.assertEqual(self.policy('developer', profile='prod', source_selection=selection), 'developer')

    def test_form_accepts_developer_mode_in_production(self):
        values = normalize_values('start', {'validation_policy': 'developer'})
        self.assertEqual(values['source_selection'], 'automatic')
        self.assertEqual(values['source_root'], '')
        self.assertEqual(values['validation_policy'], 'developer')
        for selection in ('automatic', 'explicit'):
            with self.subTest(selection=selection):
                values = normalize_values('start', {'validation_policy': 'developer', 'profile': 'prod',
                                                     'source_selection': selection})
                self.assertEqual(values['validation_policy'], 'developer')
        for selection in ('', 'invalid'):
            with self.subTest(selection=selection), self.assertRaises(FormError):
                normalize_values('start', {'validation_policy': 'developer', 'source_selection': selection})

    def test_blocked_profile_can_open_without_losing_the_failure(self):
        states = ManagerTaskStates()
        states.handle_event({'type': 'profile', 'profile': 'dev', 'status': 'blocked',
                             'detail': 'Profile validation failed.'})
        presentation = states.profile_presentation('dev')
        self.assertEqual(presentation['action'], 'ensure')
        self.assertEqual(presentation['label'], 'AW Center’ı aç')
        self.assertEqual(presentation['status'], 'blocked')
        self.assertEqual(presentation['detail'], 'Profile validation failed.')

    def test_startup_malformed_policy_preserves_safe_default(self):
        for value in (None, [], False, 'unknown'):
            with self.subTest(value=value):
                restored = paths.startup_values({'validation_policy': value}, None)
                self.assertEqual(restored['validation_policy'], 'developer')

    def test_startup_retains_developer_with_automatic_source(self):
        for profile in ('dev', 'prod'):
            with self.subTest(profile=profile):
                saved = {'profile': profile, 'source_selection': 'automatic', 'validation_policy': 'developer'}
                self.assertEqual(paths.startup_values(saved, None)['validation_policy'], 'developer')

    def test_startup_source_override_resets_full_validation_but_same_source_retains_it(self):
        saved = {'source_root': '/source', 'source_selection': 'explicit', 'profile': 'dev',
                 'validation_policy': 'managed'}
        self.assertEqual(paths.startup_values(saved, None)['validation_policy'], 'managed')
        self.assertEqual(paths.startup_values(saved, Path('/source'))['validation_policy'], 'managed')
        self.assertEqual(paths.startup_values(saved, Path('/different'))['validation_policy'], 'developer')

    def test_returning_media_restores_its_explicit_policy(self):
        import hashlib
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            (directory / 'manager-manifest.json').write_text(json.dumps({'format_version': 2, 'complete': True}))
            context = hashlib.sha256(('\0'.join([str(directory), ''])).encode()).hexdigest()
            saved = {'_media_context': 'a' * 64, 'validation_policy': 'managed',
                     '_contexts': {context: {'source_root': '/source', 'source_selection': 'explicit',
                                            'profile': 'dev', 'validation_policy': 'managed'}}}
            with patch.object(paths.sys, 'frozen', True, create=True), \
                 patch.object(paths.sys, 'executable', str(directory / 'manager.exe')):
                self.assertEqual(paths.startup_values(saved, None)['validation_policy'], 'managed')
