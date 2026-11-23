import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher.model import LauncherError
from scripts.launcher_test_support import create_project
from scripts.manager import profile_resources as resources


class ProfileResourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = create_project(Path(temporary.name).resolve())
        self.values = {'profile': 'dev', 'source_root': str(self.project.root),
                       'python_command': str(Path(sys._base_executable).resolve()), 'source_mode': 'online'}
        self.notifications = []
        self.lock = self.project.frontend / 'package-lock.json'
        self.lock.write_text(json.dumps({'packages': {'': {}, 'node_modules/example': {'version': '2.0.0'}}}))

    def notify(self, kind, text):
        self.notifications.append((kind, text))

    def test_default_and_alternative_target_leave_existing_venv_untouched(self):
        project = resources.selected_project(dict(self.values, python_command=''))
        self.assertEqual(project.venv, self.project.root / '.venv')
        project.venv.mkdir()
        cfg = project.venv / 'pyvenv.cfg'
        cfg.write_text('executable = different-base\n')
        alternate = resources.selected_project(self.values)
        self.assertTrue(alternate.venv.is_relative_to(project.root / '.runtime/venvs'))
        production = resources.selected_project(dict(self.values, profile='prod'))
        self.assertNotEqual(alternate.python, production.python)
        self.assertFalse(alternate.venv.exists())
        cfg.write_text('executable = ' + self.values['python_command'] + '\n')
        self.assertEqual(resources.selected_project(self.values).venv, project.venv)

    def test_check_lists_real_missing_names_and_leaves_fresh_project_untouched(self):
        self.project.requirements.write_text("Demo==1.0\nunused==2 ; python_version < '3'\n")
        with patch.object(resources, 'node_environment', return_value={}) as node, \
                patch.object(resources, 'fetch_artifact', side_effect=AssertionError('download')), \
                patch.object(resources, 'capture', side_effect=AssertionError('install')):
            resources.execute('check', self.values, self.notify)
        self.assertIn('Demo 1.0', str(self.notifications))
        self.assertNotIn('unused', str(self.notifications))
        self.assertIn('example@2.0.0', str(self.notifications))
        self.assertFalse(self.project.venv.exists())
        self.assertFalse((self.project.root / '.runtime').exists())
        node.assert_called_once_with(None, verify=True)

    def test_run_path_selection_works_even_if_both_lock_files_are_absent(self):
        self.project.requirements.unlink()
        self.lock.unlink()
        self.project.package_json.unlink()
        self.assertEqual(resources.selected_project(self.values).python, self.project.python)
        with self.assertRaises(LauncherError) as error:
            resources.execute('check', self.values, self.notify)
        for path in (self.project.requirements, self.project.package_json, self.lock):
            self.assertIn(str(path), str(error.exception))

    def test_npm_matches_disk_and_platform_even_with_a_stale_hidden_lock(self):
        windows = {'optional': True, 'version': '2', 'os': ['win32'], 'cpu': ['x64']}
        self.lock.write_text(json.dumps({'packages': {'': {}, 'node_modules/native': windows,
            'node_modules/apple': dict(windows, os=['darwin']), 'node_modules/a/node_modules/b': {'version': '1'}}}))
        root = self.project.frontend / 'node_modules'
        (root / 'native').mkdir(parents=True)
        (root / 'native/package.json').write_text('{"version":"1"}')
        (root / '.package-lock.json').write_bytes(self.lock.read_bytes())
        differences = resources._missing_frontend(self.project)
        self.assertEqual(differences, [resources.PackageDifference('native@2', '1'),
                                      resources.PackageDifference('a/node_modules/b@1', None)])
        resources._report(self.notify, 'Frontend', differences)
        self.assertIn('native@2 (kurulu 1)', str(self.notifications))
        self.assertIn('Eksik (1)', str(self.notifications))

    def test_source_modes_have_separate_inputs_and_no_public_corporate_fallback(self):
        values = dict(self.values, python_index_url='https://python.test/simple', npm_registry_url='')
        self.assertEqual(resources._resource_source(values, 'python'), ['--index-url', 'https://pypi.org/simple'])
        values.update(source_mode='corporate')
        self.assertEqual(resources._resource_source(values, 'python'), ['--index-url', 'https://python.test/simple'])
        with self.assertRaises(LauncherError):
            resources._resource_source(values, 'npm')
        values.update(source_mode='offline', npm_cache_dir=str(self.project.root))
        self.assertEqual(resources._resource_source(values, 'npm'), ['--offline', '--cache', str(self.project.root)])
        with self.assertRaises(LauncherError):
            resources._resource_source(values, 'python')

    def test_corporate_npm_lock_targets_exact_registry_subpath_and_preserves_source_integrity(self):
        package = {'version': '2.0.0', 'integrity': 'sha512-fixture',
                   'resolved': 'https://registry.npmjs.org/@sample/a/-/a-2.0.0.tgz'}
        self.lock.write_text(json.dumps({'packages': {'': {}, 'node_modules/@sample/a': package}}))
        original = self.lock.read_bytes()
        output = self.project.root / 'staged.json'
        registry = 'https://repo.example/repository/npm-group/'
        resources._stage_npm_lock(self.lock, output, registry)
        staged = json.loads(output.read_text())['packages']['node_modules/@sample/a']
        self.assertEqual(staged, {**package, 'resolved': registry + '@sample/a/-/a-2.0.0.tgz'})
        self.assertEqual(self.lock.read_bytes(), original)
        self.assertEqual(resources._resource_source(dict(source_mode='corporate', npm_registry_url=registry), 'npm'),
                         ['--registry', registry, '--replace-registry-host=never'])
        package['resolved'] = 'https://another.example/a.tgz'
        self.lock.write_text(json.dumps({'packages': {'node_modules/@sample/a': package}}))
        with self.assertRaises(LauncherError):
            resources._stage_npm_lock(self.lock, output, registry)

    def test_real_wheel_install_is_local_and_second_install_reuses_exact_versions(self):
        wheels = self.project.root / 'wheels'
        wheels.mkdir()
        with ZipFile(wheels / 'aw_sample-1.0-py3-none-any.whl', 'w') as wheel:
            prefix = 'aw_sample-1.0.dist-info/'
            wheel.writestr(prefix + 'METADATA', 'Metadata-Version: 2.1\nName: aw-sample\nVersion: 1.0\n')
            wheel.writestr(prefix + 'WHEEL', 'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
            wheel.writestr(prefix + 'RECORD', ''.join(prefix + name + ',,\n' for name in ('METADATA', 'WHEEL', 'RECORD')))
        self.project.requirements.write_text('aw-sample==1.0\n')
        self.values.update(source_mode='offline', wheels_dir=str(wheels))
        settings = SourceSettings(mode='offline')
        resources._python_resources(self.project, self.values, settings, self.notify)
        self.assertEqual(resources._missing_python(self.project, self.project.python), [])
        self.project.requirements.write_text('aw-sample==2.0\n')
        self.assertEqual(resources._missing_python(self.project, self.project.python),
                         [resources.PackageDifference('aw-sample==2.0', '1.0')])
        self.project.requirements.write_text('aw-sample==1.0\n')
        self.values.pop('wheels_dir')
        with patch.object(resources, 'capture', wraps=resources.capture) as capture:
            resources._python_resources(self.project, self.values, settings, self.notify)
        self.assertEqual(capture.call_count, 1)
        self.assertIn('check', capture.call_args.args[0])

    def test_failed_npm_install_keeps_working_tree(self):
        target = self.project.frontend / 'node_modules'
        target.mkdir()
        valuable = target / 'existing'
        valuable.write_text('preserve')
        settings = SourceSettings(mode='offline')
        self.values.update(source_mode='offline', npm_cache_dir=str(self.project.root))
        (self.project.root / '_cacache').mkdir()
        with patch.object(resources, 'node_environment', return_value={
                'AWCENTER_MANAGED_NODE': 'node', 'AWCENTER_MANAGED_NPM_CLI': 'npm.js'}), \
                patch.object(resources, 'capture', return_value=subprocess.CompletedProcess([], 1, '', '')):
            with self.assertRaises(LauncherError):
                resources._frontend_resources(self.project, self.values, settings, self.notify)
        self.assertEqual(valuable.read_text(), 'preserve')

    def test_run_resolves_node_without_spawning_or_installing_anything(self):
        node = self.project.root / 'node.exe'
        npm = self.project.root / 'npm-cli.js'
        node.touch()
        npm.touch()
        with patch.object(resources, '_managed_tool', return_value=None), \
                patch.object(resources.system_node, '_candidates', return_value=[node]), \
                patch.object(resources.system_node, '_npm_candidates', return_value=[npm]), \
                patch.object(resources.system_node, 'validate_node', side_effect=AssertionError('probe')), \
                patch.object(resources, '_install_tool', side_effect=AssertionError('install')):
            self.assertEqual(resources.node_environment()['AWCENTER_MANAGED_NPM_CLI'], str(npm))

    def test_local_renderer_runs_on_install_with_current_packages_and_never_on_check_or_prod(self):
        target = self.project.frontend / 'node_modules/example'
        target.mkdir(parents=True)
        (target / 'package.json').write_text('{"version":"2.0.0"}')
        tools = {'AWCENTER_MANAGED_NODE': 'node', 'AWCENTER_MANAGED_NPM_CLI': 'npm-cli.js'}
        with patch.object(resources, 'node_environment', return_value=tools), \
                patch.object(resources, '_prepare_renderer') as prepare:
            resources._frontend_resources(self.project, self.values, None, self.notify)
            resources._frontend_resources(self.project, dict(self.values, profile='prod'), SourceSettings(), self.notify)
            prepare.assert_not_called()
            resources._frontend_resources(self.project, self.values, SourceSettings(), self.notify)
            prepare.assert_called_once_with(self.project, tools, self.notify)

    def test_install_remembers_later_valid_node_for_probe_free_run(self):
        old, valid = self.project.root / 'old-node.exe', self.project.root / 'valid-node.exe'
        cli = self.project.root / 'npm-cli.js'
        for path in (old, valid, cli):
            path.touch()
        self.lock.write_text('{"packages":{"":{}}}')
        with patch.object(resources, 'worker_directory', return_value=self.project.root), \
                patch.object(resources, '_managed_tool', return_value=None), \
                patch.object(resources.system_node, '_candidates', side_effect=lambda: iter([old, valid])), \
                patch.object(resources.system_node, '_npm_candidates', return_value=[cli]), \
                patch.object(resources.system_node, 'find_npm_cli', return_value=cli), \
                patch.object(resources.system_node, 'validate_node', side_effect=[
                    resources.system_node.SystemNodeError('version'), valid]) as probe:
            resources._frontend_resources(self.project, dict(self.values, profile='prod'), SourceSettings(), self.notify)
            self.assertEqual(resources.node_environment()['AWCENTER_MANAGED_NODE'], str(valid))
            self.assertEqual(probe.call_count, 2)

    def test_renderer_failure_with_existing_output_does_not_report_ready(self):
        script = self.project.frontend / 'scripts/build-mermaid-renderer.mjs'
        script.parent.mkdir()
        script.touch()
        output = self.project.frontend / '.cache/mermaid/renderer.js'
        output.parent.mkdir(parents=True)
        output.write_text('old')
        with patch.object(resources, 'controlled_run', return_value=subprocess.CompletedProcess([], 1)) as run:
            with self.assertRaisesRegex(LauncherError, 'Mermaid'):
                resources._prepare_renderer(self.project, {'AWCENTER_MANAGED_NODE': 'node'}, self.notify)
        self.assertEqual(run.call_args.args[0], ['node', str(script), '--dev'])
        self.assertEqual(run.call_args.kwargs['cwd'], self.project.frontend)

    def test_other_ecosystem_is_checked_when_python_missing(self):
        with patch.object(resources, '_python_resources', side_effect=LauncherError('Python eksik')), \
                patch.object(resources, '_frontend_resources') as frontend:
            with self.assertRaisesRegex(LauncherError, 'Python eksik'):
                resources.execute('check', self.values, self.notify)
        frontend.assert_called_once()

    def test_python_choices_include_other_installed_minors_and_de_duplicate(self):
        paths = [self.project.root / name for name in ('first', 'second', 'alias')]
        versions = {(paths[0]): ((3, 15, 1), paths[0]), paths[1]: ((3, 11, 4), paths[1]),
                    paths[2]: ((3, 11, 4), paths[1])}
        with patch.object(resources, '_python_candidates', return_value=paths), \
                patch.object(resources, '_python_hint', side_effect=versions.get):
            self.assertEqual([path for label, path in resources.python_choices()], [str(paths[1]), str(paths[0])])
