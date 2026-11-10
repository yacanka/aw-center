"""Locked sample selection and package-manager metadata contracts."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.launcher_test_support import create_project
from scripts.manager import source_packages as packages
from scripts.manager.source_probe import ProbeFailure, Transfer


def metadata(body, *, url='https://repo.invalid/simple/demo/', content_type='application/json'):
    encoded = body.encode('utf-8') if isinstance(body, str) else json.dumps(body).encode('utf-8')
    return Transfer(url, len(encoded), {}, encoded, content_type)


class PackageMetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = create_project(self.root)
        self.digest = hashlib.sha256(b'wheel bytes').hexdigest()

    def test_python_sample_uses_exact_unconditional_pin_and_normalizes_project_name(self):
        self.project.requirements.write_text(
            "conditional==9 ; sys_platform == 'linux'\nDemo__Package==1.2.3\nother==8\n")
        sample = packages.python_sample(self.project)
        self.assertEqual((sample.name, sample.version), ('demo-package', '1.2.3'))

    def test_python_html_resolves_exact_universal_wheel_and_fragment_hash_relative_to_final_url(self):
        sample = packages.Sample('demo', '1.2.3')
        body = (f'<a href="../../files/demo-1.2.3-py3-none-any.whl#sha256={self.digest}">wheel</a>'
                '<a href="demo-2.0-py3-none-any.whl">other version</a>')
        selected = packages.python_file(metadata(body, content_type='text/html'), sample)
        self.assertEqual(selected.url, 'https://repo.invalid/files/demo-1.2.3-py3-none-any.whl')
        self.assertEqual(selected.expected, {'sha256': (self.digest,)})

    def test_python_json_resolves_file_url_and_strong_digest(self):
        body = {'meta': {'api-version': '1.0'}, 'name': 'demo', 'files': [{
            'filename': 'demo-1.2.3-py2.py3-none-any.whl',
            'url': 'https://files.invalid/demo.whl?token=private-token',
            'hashes': {'sha256': self.digest},
        }]}
        selected = packages.python_file(metadata(body), packages.Sample('demo', '1.2.3'))
        self.assertEqual(selected.url, body['files'][0]['url'])
        self.assertEqual(selected.expected, {'sha256': (self.digest,)})

    def test_python_login_page_does_not_count_as_package_index(self):
        body = '<html><form><input type="password"></form><a href="/login">Login</a></html>'
        with self.assertRaises(ProbeFailure) as caught:
            packages.python_file(metadata(body, content_type='text/html'), packages.Sample('demo', '1.2.3'))
        self.assertEqual(caught.exception.code, 'source_metadata_invalid')

    def test_python_missing_pin_does_not_silently_download_another_version(self):
        body = {'name': 'demo', 'files': [{'filename': 'demo-9.0-py3-none-any.whl',
                                         'url': 'https://files.invalid/other.whl', 'hashes': {}}]}
        with self.assertRaises(ProbeFailure) as caught:
            packages.python_file(metadata(body), packages.Sample('demo', '1.2.3'))
        self.assertEqual(caught.exception.code, 'source_version_missing')

    def test_npm_sample_retains_scoped_name_exact_version_and_lock_integrity(self):
        digest = hashlib.sha512(b'package').digest()
        integrity = 'sha512-' + base64.b64encode(digest).decode('ascii')
        (self.project.frontend / 'package-lock.json').write_text(json.dumps({'packages': {
            '': {'version': '1.0'}, 'node_modules/@scope/demo': {'version': '2.1.0', 'integrity': integrity},
        }}))
        sample = packages.npm_sample(self.project)
        self.assertEqual((sample.name, sample.version), ('@scope/demo', '2.1.0'))
        self.assertEqual(sample.expected, {'sha512': (digest.hex(),)})

    def test_npm_uses_exact_metadata_version_but_lock_digest_is_authoritative(self):
        sample = packages.Sample('@scope/demo', '2.1.0', {'sha512': ('a' * 128,)})
        body = {'name': sample.name, 'versions': {'2.1.0': {
            'name': sample.name, 'version': sample.version,
            'dist': {'tarball': 'https://files.invalid/package.tgz',
                     'integrity': 'sha512-' + base64.b64encode(b'other' * 13).decode('ascii')},
        }}}
        selected = packages.npm_file(metadata(body), sample)
        self.assertEqual(selected.url, 'https://files.invalid/package.tgz')
        self.assertEqual(selected.expected, sample.expected)

    def test_npm_missing_version_and_mismatched_identity_are_explicit(self):
        sample = packages.Sample('demo', '1.2.3')
        for body, code in (({'name': 'demo', 'versions': {}}, 'source_version_missing'),
                           ({'name': 'other', 'versions': {}}, 'source_metadata_invalid')):
            with self.subTest(code=code), self.assertRaises(ProbeFailure) as caught:
                packages.npm_file(metadata(body), sample)
            self.assertEqual(caught.exception.code, code)

    def test_invalid_json_and_file_addresses_do_not_expose_metadata(self):
        sample = packages.Sample('demo', '1.2.3')
        for body in ('<html>private-login</html>', '["private-data"]',
                     {'name': 'demo', 'versions': {'1.2.3': {'name': 'demo', 'version': '1.2.3',
                      'dist': {'tarball': 'http://user:private-secret@files.invalid/file'}}}}):
            with self.subTest(body=body), self.assertRaises(ProbeFailure) as caught:
                packages.npm_file(metadata(body), sample)
            self.assertNotIn('private-', str(caught.exception))

    def test_invalid_expected_hash_is_not_accepted_as_metadata(self):
        body = {'name': 'demo', 'files': [{'filename': 'demo-1.2.3-py3-none-any.whl',
                'url': 'https://files.invalid/file.whl', 'hashes': {'sha256': 'private-invalid'}}]}
        with self.assertRaises(ProbeFailure) as caught:
            packages.python_file(metadata(body), packages.Sample('demo', '1.2.3'))
        self.assertEqual(caught.exception.code, 'source_metadata_invalid')
        self.assertNotIn('private-', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
