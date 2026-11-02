"""Read-only feature diagnosis and immutable asset import regressions."""
import importlib
import json
import hashlib
import zipfile
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.launcher.model import LauncherError
from scripts.test_launcher_bundle import project_at


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.features = importlib.import_module('scripts.launcher.installation_features')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        from scripts.launcher.installation_permissions import secure_path
        secure_path(self.root)
        self.project = project_at(self.root / 'project')
        self.profile = {'name':'dev', 'installation_home':str(self.root / 'home'),
                        'env_file':str(self.root / 'private/dev.env')}

    def test_inventory_reports_private_inputs_and_never_exposes_config_values(self):
        values = {'JIRA_ENABLED':'True', 'JIRA_URL':'https://private-host.example',
                  'JIRA_SESSION_ENCRYPTION_KEY':'secret-value', 'AI_API_TOKEN':'secret-token'}
        with patch.object(self.features, 'read_profile_environment', return_value=values), \
             patch.object(self.features.shutil, 'which', return_value=None):
            report = self.features.inspect_features(self.project, self.profile)
        rows = {row['name']:row for row in report}
        self.assertEqual(rows['JIRA']['status'], 'configured')
        self.assertIn('not verified', rows['JIRA']['detail'])
        for name in ('ffmpeg', 'ffprobe', 'soffice', 'pdftoppm', 'DOORS',
                     'Word COM', 'Outlook COM', 'PROJECT_CONFIGURATION_FILE',
                     'DDF_ASSESSMENT_POLICY_FILE', 'GOKBEY_DCC_POLICY_FILE',
                     'opus-mt-tr-en', 'opus-mt-en-tr', 'paraphrase-multilingual',
                     'ms-marco-cross-encoder', 'document-templates'):
            self.assertIn(name, rows)
        serialized = json.dumps(report)
        self.assertNotIn('private-host', serialized)
        self.assertNotIn('secret-value', serialized)
        self.assertNotIn('secret-token', serialized)
        self.assertFalse((self.root / 'home').exists())

    def test_canonical_native_tool_and_mail_settings_are_inspected(self):
        values = {'PDFTOPPM_BIN':'approved-pdf-tool', 'AWCENTER_MAIL_TRANSPORT':'django',
                  'EMAIL_HOST':'private-smtp-host'}
        with patch.object(self.features, 'read_profile_environment', return_value=values), \
             patch.object(self.features.shutil, 'which', side_effect=lambda name, **kwargs: '/approved/tool' if name == 'approved-pdf-tool' else None):
            report = self.features.inspect_features(self.project, self.profile)
        rows = {row['name']:row for row in report}
        self.assertEqual(rows['pdftoppm']['status'], 'configured')
        self.assertEqual(rows['SMTP']['status'], 'configured')
        self.assertIn('PowerPoint COM', rows)
        self.assertNotIn('private-smtp-host', json.dumps(report))

    def test_model_inventory_does_not_hash_large_model_files(self):
        model = self.root / 'model'
        model.mkdir()
        (model / 'weights.safetensors').write_bytes(b'synthetic model weight')
        values = {'WORD_TRANSLATION_TR_EN_MODEL':str(model)}
        with patch.object(self.features, 'read_profile_environment', return_value=values), \
             patch.object(self.features, 'install_inventory', side_effect=AssertionError('unexpected full model hashing')):
            rows = {row['name']:row for row in self.features.inspect_features(self.project, self.profile)}
        self.assertEqual(rows['opus-mt-tr-en']['status'], 'configured')

    def test_empty_model_directory_is_missing(self):
        model = self.root / 'empty-model'
        model.mkdir()
        values = {'WORD_TRANSLATION_TR_EN_MODEL':str(model)}
        with patch.object(self.features, 'read_profile_environment', return_value=values):
            rows = {row['name']:row for row in self.features.inspect_features(self.project, self.profile)}
        self.assertEqual(rows['opus-mt-tr-en']['status'], 'missing')

    def test_missing_licensed_software_is_not_downloaded(self):
        with patch.object(self.features, 'read_profile_environment', return_value={}), \
             patch.object(self.features, 'load_catalog', return_value={}), \
             patch.object(self.features, 'fetch_artifact') as fetch:
            rows = self.features.install_features(self.project, self.profile, None)
        fetch.assert_not_called()
        self.assertIn('DOORS', {row['name'] for row in rows})

    def test_asset_import_verifies_all_hashes_before_creating_destination(self):
        source = self.root / 'assets'
        (source / 'document-templates').mkdir(parents=True)
        (source / 'document-templates/cover.docx').write_bytes(b'not-approved')
        (source / 'asset-manifest.json').write_text(json.dumps({
            'format_version':1, 'asset_set':'approved-v1',
            'artifacts':[{'path':'document-templates/cover.docx', 'size':12, 'sha256':'a'*64}],
        }))
        with self.assertRaises(LauncherError):
            self.features.import_asset_set(source, self.root / 'home')
        self.assertFalse((self.root / 'home').exists())

    def test_explicit_owner_restricted_catalog_installs_native_tool_without_commands(self):
        from scripts.launcher.installation_sources import SourceSettings
        source = self.root / 'native-source'
        source.mkdir(mode=0o700)
        from scripts.launcher.installation_permissions import secure_path
        secure_path(source)
        archive = source / 'ffmpeg.zip'
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('bin/ffmpeg.exe', b'synthetic approved executable')
            package.writestr('bin/ffprobe.exe', b'synthetic approved probe')
        catalog = source / 'approved.json'
        catalog.write_text(json.dumps({'format_version':1, 'artifacts':[{
            'name':'ffmpeg', 'version':'1.0', 'filename':'ffmpeg.zip',
            'url':'https://publisher.example/ffmpeg.zip',
            'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'archive':'zip', 'executable':'bin/ffmpeg.exe',
        }]}))
        from scripts.launcher.installation_permissions import secure_path
        secure_path(catalog)
        with patch.object(self.features, 'read_profile_environment', return_value={}), \
             patch('scripts.launcher.installation_sources._retrieve', return_value=False):
            self.features.install_features(self.project, self.profile,
                                           SourceSettings(offline_dir=source), feature_catalog=catalog)
        installed = self.root / 'home/tools/ffmpeg-1.0/bin/ffmpeg.exe'
        self.assertEqual(installed.read_bytes(), b'synthetic approved executable')
        overrides = self.features.feature_environment(self.project, self.profile)
        self.assertEqual(overrides['FFMPEG_EXECUTABLE'], str(installed))
        self.assertTrue((self.root / 'home/config/features.catalog.json').is_file())

    def test_operator_catalog_cannot_authorize_arbitrary_command_or_licensed_software(self):
        catalog = self.root / 'approved.json'
        catalog.write_text(json.dumps({'format_version':1, 'artifacts':[{
            'name':'office', 'version':'1.0', 'filename':'office.zip',
            'url':'https://publisher.example/office.zip', 'sha256':'a'*64,
            'archive':'zip', 'executable':'setup.exe', 'command':'delete-state',
        }]}))
        from scripts.launcher.installation_permissions import secure_path
        secure_path(catalog)
        with self.assertRaises(LauncherError):
            self.features.read_feature_catalog(catalog)
        self.assertFalse((self.root / 'home').exists())

    def test_owner_catalog_rejects_world_readable_approval_file(self):
        catalog = self.root / 'approved.json'
        catalog.write_text('{"format_version":1,"artifacts":[]}')
        catalog.chmod(0o644)
        if self.features.os.name == 'nt':
            self.skipTest('POSIX mode fixture; Windows ACLs have separate coverage')
        with self.assertRaises(LauncherError):
            self.features.read_feature_catalog(catalog)

    def test_approved_asset_import_is_idempotent_and_never_overwrites_changed_set(self):
        source = self.root / 'assets'
        (source / 'document-templates').mkdir(parents=True)
        payload = b'approved document template'
        (source / 'document-templates/cover.docx').write_bytes(payload)
        manifest = {'format_version':1, 'asset_set':'approved-v1', 'artifacts':[{
            'path':'document-templates/cover.docx', 'size':len(payload),
            'sha256':hashlib.sha256(payload).hexdigest(),
        }]}
        (source / 'asset-manifest.json').write_text(json.dumps(manifest))
        destination = self.features.import_asset_set(source, self.root / 'home')
        self.assertEqual(self.features.import_asset_set(source, self.root / 'home'), destination)
        (destination / 'document-templates/cover.docx').write_bytes(b'tampered')
        with self.assertRaises(LauncherError):
            self.features.import_asset_set(source, self.root / 'home')
        self.assertEqual((destination / 'document-templates/cover.docx').read_bytes(), b'tampered')


if __name__ == '__main__':
    unittest.main()
