"""Developer validation is an explicit dev/source choice, never an implicit default."""
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

    def test_missing_policy_defaults_to_managed(self):
        self.assertEqual(self.policy(), 'managed')
        self.assertEqual(normalize_values('start', {})['validation_policy'], 'managed')

    def test_unknown_policies_are_safe_structured_errors(self):
        for value in ('', None, False, [], 'Developer', 'unknown-token=secret'):
            with self.subTest(value=value), self.assertRaises(LauncherError) as caught:
                self.policy(value)
            self.assertEqual(caught.exception.code, 'invalid_validation_policy')
            self.assertEqual(caught.exception.field, 'validation_policy')
            self.assertNotIn('secret', str(caught.exception))

    def test_developer_requires_dev_and_explicit_source_when_supplied(self):
        self.assertEqual(self.policy('developer'), 'developer')
        self.assertEqual(self.policy('developer', source_selection='explicit'), 'developer')
        with self.assertRaises(LauncherError):
            self.policy('developer', profile='prod', source_selection='explicit')
        for selection in ('automatic', '', False):
            with self.subTest(selection=selection), self.assertRaises(LauncherError) as caught:
                self.policy('developer', source_selection=selection)
            self.assertEqual(caught.exception.field, 'source_root')

    def test_form_rejects_developer_for_unselected_source_or_prod(self):
        for values in ({'source_selection': 'automatic'}, {'profile': 'prod', 'source_selection': 'explicit'}):
            with self.subTest(values=values), self.assertRaises(FormError):
                normalize_values('start', {'validation_policy': 'developer', **values})

    def test_blocked_profile_full_verification_action_is_labelled(self):
        states = ManagerTaskStates()
        states.handle_event({'type': 'profile', 'profile': 'dev', 'status': 'blocked'})
        presentation = states.profile_presentation('dev')
        self.assertEqual(presentation['action'], 'doctor')
        self.assertEqual(presentation['label'], 'Tam doğrula')

    def test_startup_malformed_policy_preserves_safe_default(self):
        for value in (None, [], False, 'unknown'):
            with self.subTest(value=value):
                restored = paths.startup_values({'validation_policy': value}, None)
                self.assertEqual(restored['validation_policy'], 'managed')

    def test_startup_source_override_resets_developer_but_same_source_retains_it(self):
        saved = {'source_root': '/source', 'source_selection': 'explicit', 'profile': 'dev',
                 'validation_policy': 'developer'}
        self.assertEqual(paths.startup_values(saved, None)['validation_policy'], 'developer')
        self.assertEqual(paths.startup_values(saved, Path('/source'))['validation_policy'], 'developer')
        self.assertEqual(paths.startup_values(saved, Path('/different'))['validation_policy'], 'managed')

    def test_new_media_context_resets_developer_even_when_restoring_prior_context(self):
        import hashlib
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'manager-manifest.json').write_text(json.dumps({'format_version': 2, 'complete': True}))
            context = hashlib.sha256(('\0'.join([str(directory), ''])).encode()).hexdigest()
            saved = {'_media_context': 'a' * 64, 'validation_policy': 'developer',
                     '_contexts': {context: {'source_root': '/source', 'source_selection': 'explicit',
                                            'profile': 'dev', 'validation_policy': 'developer'}}}
            with patch.object(paths.sys, 'frozen', True, create=True), \
                 patch.object(paths.sys, 'executable', str(directory / 'manager.exe')):
                self.assertEqual(paths.startup_values(saved, None)['validation_policy'], 'managed')
