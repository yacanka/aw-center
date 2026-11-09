"""Explicit TLS replacements repair stale paths without bypassing profile safety."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from datetime import timedelta
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher.discovery import discover_project
from scripts.launcher import installation_profiles as profiles
from scripts.launcher.model import LauncherError
from scripts.manager import ensure, operations, payload
from scripts.test_launcher_bundle import project_at


class TlsRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        environment = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.home = self.root / 'AWCenter'
        checkout = project_at(self.root / 'checkout')
        checkout.package_json.write_text('{"dependencies":{"vue":"3"}}')
        media = self.root / 'media'
        payload.prepare_source_payload(checkout, media)
        self.project = discover_project(payload.stage_production_source(media, self.home))
        self.certificate = self.root / 'certificate.pem'
        self.key = self.root / 'key.pem'
        self.certificate.write_text('synthetic certificate fixture')
        self.key.write_text('synthetic private-key fixture')
        self.original = profiles.provision_profile(self.project, 'prod', self.home,
            host='192.0.2.10', tls_cert_file=self.certificate, tls_key_file=self.key)
        self.profile_path = self.home / 'config/prod.profile.json'
        self.environment_path = self.home / 'config/prod.env'
        self.pending = self.home / 'config/prod.pending.json'
        state = self.home / 'state/production'
        self.database = state / 'db.sqlite3'
        self.artifact = state / 'private_media/retained.bin'
        self.database.write_bytes(b'opaque existing database fixture')
        self.artifact.write_bytes(b'opaque private artifact fixture')

    def args(self, **values):
        args = operations.arguments({'action': 'ensure', 'profile': 'prod', **values})
        args.source_root = str(self.project.root)
        args.progress = lambda message: None
        return args

    def decoded_leaf(self, ip='192.0.2.10'):
        return patch('_ssl._test_decode_cert', return_value={
            'notBefore': 'Jan  1 00:00:00 2020 GMT', 'notAfter': 'Jan  1 00:00:00 2099 GMT',
            'subjectAltName': (('IP Address', ip),),
        })

    def move_certificate(self):
        destination = self.root / 'replacement-certificate.pem'
        self.certificate.rename(destination)
        return destination

    def snapshot(self):
        # Digests keep generated credentials out of assertion diagnostics.
        return {path.relative_to(self.home).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.home.rglob('*') if path.is_file()}

    def assert_rejected_without_writes(self, args):
        before = self.snapshot()
        for operation in (ensure.needs_preparation, ensure.prepare_connection):
            with self.subTest(operation=operation.__name__), self.assertRaises(LauncherError):
                operation(self.project, args)
            self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.pending.exists())

    def test_moved_certificate_selects_preparation_without_writes(self):
        replacement = self.move_certificate()
        before = self.snapshot()
        self.assertTrue(ensure.needs_preparation(self.project,
                                               self.args(tls_cert_file=str(replacement))))
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(importlib.util.find_spec('cryptography'), 'Certificate generation requires cryptography')
    def test_real_tls_retry_works_with_unverified_or_absent_project_python(self):
        from scripts.test_launcher_local_tls import issue_identity
        self.certificate.rename(self.root / 'old-certificate.pem')
        host = self.original['host']
        _, _, good, key = issue_identity(self.root, 'good', host=host)
        _, _, _, other_key = issue_identity(self.root, 'other', host=host)
        self.project.python.parent.mkdir(parents=True, exist_ok=True)
        self.project.python.write_bytes(b'unverified interpreter fixture')
        with patch('scripts.launcher.runtime.run', side_effect=AssertionError('Unverified project Python was invoked')):
            for label, options in (('wrong-ip', {'host': '192.0.2.11'}), ('dns-only', {'dns_san': True}),
                                   ('future', {'valid_from': timedelta(hours=1)}),
                                   ('expired', {'expired': True}), ('last-day', {'valid_for': timedelta(days=1)}),
                                   ('wrong-key', {})):
                with self.subTest(label=label):
                    _, _, cert, candidate_key = issue_identity(self.root, label, **{'host': host, **options})
                    if label == 'wrong-key':
                        candidate_key = other_key
                    before = self.snapshot()
                    with self.assertRaises(LauncherError):
                        ensure.prepare_connection(self.project, self.args(tls_cert_file=str(cert), tls_key_file=str(candidate_key)))
                    self.assertEqual(self.snapshot(), before)
                    self.assertFalse(self.pending.exists())
            self.project.python.unlink()
            self.assertTrue(ensure.prepare_connection(self.project, self.args(tls_cert_file=str(good), tls_key_file=str(key))))
        self.assertEqual(profiles.load_profile(self.project, 'prod')['tls_cert_file'], str(good))
        self.assertFalse(self.project.python.exists())

    def test_replacement_validation_returns_original_profile_for_compare_and_swap(self):
        replacement = self.move_certificate()
        before = self.snapshot()
        loaded = profiles.load_profile(self.project, 'prod', self.home,
                                       tls_replacements={'tls_cert_file': str(replacement)})
        self.assertEqual(loaded, self.original)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'prod', self.home)

    def test_replacement_scope_cannot_override_other_profile_fields(self):
        replacement = self.move_certificate()
        before = self.snapshot()
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'prod', self.home,
                tls_replacements={'tls_cert_file': str(replacement), 'host': '192.0.2.20'})
        self.assertEqual(self.snapshot(), before)

    def test_missing_certificate_without_replacement_remains_invalid(self):
        self.move_certificate()
        self.assert_rejected_without_writes(self.args())
        with self.assertRaises(LauncherError):
            profiles.load_profile(self.project, 'prod', self.home)

    def test_certificate_replacement_does_not_hide_missing_unreplaced_key(self):
        replacement = self.move_certificate()
        self.key.rename(self.root / 'moved-key.pem')
        self.assert_rejected_without_writes(self.args(tls_cert_file=str(replacement)))

    def test_invalid_replacement_paths_are_rejected_without_writes(self):
        self.move_certificate()
        inside_source = self.project.root / 'certificate.pem'
        inside_source.write_text('synthetic certificate fixture')
        candidates = (self.root / 'missing.pem', self.root, inside_source, Path('relative.pem'))
        for replacement in candidates:
            with self.subTest(kind=replacement.name):
                self.assert_rejected_without_writes(self.args(tls_cert_file=str(replacement)))

    def test_symlink_replacement_is_rejected_without_writes(self):
        replacement = self.move_certificate()
        link = self.root / 'linked-certificate.pem'
        try:
            link.symlink_to(replacement)
        except OSError:
            self.skipTest('This host does not permit creating symlinks')
        self.assert_rejected_without_writes(self.args(tls_cert_file=str(link)))

    def test_tls_replacement_does_not_bypass_invalid_existing_environment(self):
        replacement = self.move_certificate()
        original = self.environment_path.read_bytes()
        for field, value in (('SECRET_KEY', ''), ('JIRA_SESSION_ENCRYPTION_KEY', ''),
                             ('PRIVATE_MEDIA_ROOT', str(self.root / 'other-private-media'))):
            with self.subTest(field=field):
                self.environment_path.write_bytes(original)
                values = profiles.read_environment(self.environment_path)
                values[field] = value
                profiles._write_replace(self.environment_path, profiles._environment_content(values))
                self.assert_rejected_without_writes(self.args(tls_cert_file=str(replacement)))

    def test_tls_replacement_does_not_bypass_profile_identity_or_options(self):
        replacement = self.move_certificate()
        for field, value in (('source_root', str(self.root / 'other-source')),
                             ('env_file', str(self.root / 'other.env')), ('backend_port', 0)):
            with self.subTest(field=field):
                changed = {**self.original, field: value}
                profiles._write_replace(self.profile_path, json.dumps(changed))
                self.assert_rejected_without_writes(self.args(tls_cert_file=str(replacement)))

    @unittest.skipIf(os.name == 'nt', 'POSIX permission mode regression; Windows uses ACLs')
    def test_tls_replacement_does_not_repair_unsafe_private_configuration_permissions(self):
        replacement = self.move_certificate()
        self.environment_path.chmod(0o644)
        self.assert_rejected_without_writes(self.args(tls_cert_file=str(replacement)))
        self.assertEqual(self.environment_path.stat().st_mode & 0o777, 0o644)

    def test_certificate_and_key_replacement_preserves_environment_and_private_state(self):
        replacement = self.move_certificate()
        replacement_key = self.root / 'replacement-key.pem'
        self.key.rename(replacement_key)
        before = self.snapshot()
        with self.decoded_leaf(), patch('ssl.SSLContext.load_cert_chain') as load_chain, \
             patch('scripts.launcher.runtime.validate_tls_identity') as validate_identity:
            ensure.prepare_connection(self.project, self.args(
                tls_cert_file=str(replacement), tls_key_file=str(replacement_key)))
        load_chain.assert_called_once()
        self.assertEqual(load_chain.call_args.args, (str(replacement), str(replacement_key)))
        with self.assertRaises(ValueError):
            load_chain.call_args.kwargs['password']()
        validate_identity.assert_not_called()
        loaded = profiles.load_profile(self.project, 'prod', self.home)
        self.assertEqual(loaded, {**self.original, 'tls_cert_file': str(replacement),
                                  'tls_key_file': str(replacement_key)})
        after = self.snapshot()
        before.pop('config/prod.profile.json')
        after.pop('config/prod.profile.json')
        self.assertEqual(after, before)
        self.assertFalse(self.pending.exists())

    def test_invalid_certificate_content_cannot_publish_replacement(self):
        replacement = self.move_certificate()
        before = self.snapshot()
        with self.assertRaises(profiles.TLSFileError) as failure:
            ensure.prepare_connection(self.project, self.args(tls_cert_file=str(replacement)))
        self.assertEqual(failure.exception.code, 'tls_file_invalid')
        self.assertEqual(failure.exception.field, 'tls_cert_file')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.pending.exists())

    def test_identity_validation_failure_cannot_publish_replacement(self):
        replacement = self.move_certificate()
        before = self.snapshot()
        with self.decoded_leaf(ip='192.0.2.11'), self.assertRaises(profiles.TLSFileError) as failure:
            ensure.prepare_connection(self.project, self.args(tls_cert_file=str(replacement)))
        self.assertEqual(failure.exception.code, 'tls_file_san')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.pending.exists())

    def test_interrupted_profile_publish_recovers_using_original_journal_identity(self):
        replacement = self.move_certificate()
        before = self.snapshot()
        original_profile = self.profile_path.read_bytes()
        write = profiles._write_replace

        def interrupt(path, content):
            if path == self.profile_path:
                raise OSError('simulated interruption before profile publication')
            write(path, content)

        with self.decoded_leaf(), patch('ssl.SSLContext.load_cert_chain'), \
             patch.object(profiles, '_write_replace', side_effect=interrupt):
            with self.assertRaises(OSError):
                ensure.prepare_connection(self.project, self.args(tls_cert_file=str(replacement)))
        journal = json.loads(self.pending.read_text())
        self.assertEqual(journal['operation'], 'connection')
        self.assertEqual(journal['previous_profile_sha256'], hashlib.sha256(original_profile).hexdigest())
        self.assertEqual(journal['profile']['tls_cert_file'], str(replacement))
        self.assertTrue(self.profile_path.read_bytes() == original_profile,
                        'An interrupted publish must keep the original profile intact')
        self.assertTrue(ensure.needs_preparation(self.project, self.args()))
        ensure.prepare_connection(self.project, self.args())
        loaded = profiles.load_profile(self.project, 'prod', self.home)
        self.assertEqual(loaded['tls_cert_file'], str(replacement))
        after = self.snapshot()
        before.pop('config/prod.profile.json')
        after.pop('config/prod.profile.json')
        self.assertEqual(after, before)
        self.assertFalse(self.pending.exists())
