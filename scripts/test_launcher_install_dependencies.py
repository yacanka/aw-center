"""Source fallback must not disguise installation or integrity failures."""

import json
import os
import shutil
import subprocess
import ssl
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from scripts.launcher.model import LauncherError
from scripts.launcher.installation_sources import SourceSettings
from scripts.launcher_test_support import create_project


class PackageConfigurationIsolationTests(unittest.TestCase):
    def test_capture_preserves_utf8_output_under_windows_ansi_parent_encoding(self):
        from scripts.launcher.installation_dependencies import capture
        from scripts.launcher.process import operation_control
        message = 'Python ortamı hazır: İışğ 中文'
        program = 'import sys; print(sys.argv[1]); print(sys.argv[1], file=sys.stderr)'
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            for utf8, encoding in (('1', 'utf-8'), ('0', 'ascii')):
                with self.subTest(encoding=encoding), operation_control(threading.Event()), \
                     mock.patch('subprocess._text_encoding', return_value='cp1254'), \
                     mock.patch.dict(os.environ, {'PYTHONIOENCODING': encoding, 'PYTHONUTF8': utf8}):
                    result = capture([sys.executable, '-c', program, message], project)
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stdout.strip(), message)
                    self.assertEqual(result.stderr.strip(), message)

    def test_legacy_diagnostic_bytes_do_not_mask_package_exit_status(self):
        from scripts.launcher.installation_dependencies import capture, _succeeded, PackageCommandError
        program = 'import os,sys; os.write(2, b"permission denied: \\xfe\\xff"); raise SystemExit(int(sys.argv[1]))'
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            for exit_code in (0, 17):
                with self.subTest(exit_code=exit_code), \
                        mock.patch('subprocess._text_encoding', return_value='utf-8'):
                    result = capture([sys.executable, '-c', program, str(exit_code)], project)
                    self.assertEqual(result.returncode, exit_code)
                    if exit_code == 0:
                        _succeeded(result, 'Python paket kurulumu')
                    else:
                        with self.assertRaises(PackageCommandError) as caught:
                            _succeeded(result, 'Python paket kurulumu')
                        self.assertEqual(caught.exception.code, 'package_access_denied')

    def test_capture_provides_distinct_empty_npm_configs_and_removes_them_after_exit(self):
        from scripts.launcher.installation_dependencies import capture
        program = '''import json, os, pathlib, sys
paths = [os.environ['NPM_CONFIG_USERCONFIG'], os.environ['NPM_CONFIG_GLOBALCONFIG']]
print(json.dumps({'paths': paths, 'contents': [pathlib.Path(path).read_text() for path in paths],
                  'inherited': any(name in os.environ for name in ('NPM_CONFIG_REGISTRY', 'npm_config_registry', 'NPM_CONFIG__AUTH', 'PIP_INDEX_URL'))}))
sys.exit(int(sys.argv[1]))
'''
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            for exit_code in (0, 7):
                with self.subTest(exit_code=exit_code), \
                     mock.patch.dict(os.environ, {'NPM_CONFIG_REGISTRY': 'https://untrusted.invalid',
                                                 'npm_config_registry': 'https://untrusted.invalid',
                                                 'NPM_CONFIG__AUTH': 'inherited-credential-fixture',
                                                 'PIP_INDEX_URL': 'https://untrusted.invalid'}):
                    result = capture([sys.executable, '-c', program, str(exit_code)], project)
                    self.assertEqual(result.returncode, exit_code)
                    observed = json.loads(result.stdout)
                    self.assertNotEqual(*observed['paths'])
                    self.assertEqual(observed['contents'], ['', ''])
                    self.assertFalse(observed['inherited'])
                    self.assertTrue(all(not Path(path).exists() for path in observed['paths']))

    def test_capture_cleans_npm_configs_after_start_error_timeout_and_cancellation(self):
        from scripts.launcher import installation_dependencies as dependencies
        from scripts.launcher.process import OperationCancelled
        cases = ((OSError('fixture'), OSError),
                 (subprocess.TimeoutExpired(['fixture'], 1), LauncherError),
                 (OperationCancelled('fixture'), OperationCancelled))
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            for error, expected in cases:
                observed = []
                def fail(command, **options):
                    paths = [Path(options['env'][name]) for name in
                             ('NPM_CONFIG_USERCONFIG', 'NPM_CONFIG_GLOBALCONFIG')]
                    self.assertNotEqual(*paths)
                    self.assertTrue(all(path.is_file() and path.read_bytes() == b'' for path in paths))
                    observed.extend(paths)
                    raise error
                with self.subTest(error=type(error).__name__), \
                     mock.patch.object(dependencies, 'controlled_run', side_effect=fail):
                    with self.assertRaises(expected):
                        dependencies.capture(['fixture'], project)
                self.assertEqual(len(observed), 2)
                self.assertTrue(all(not path.exists() for path in observed))

    def test_capture_preserves_explicit_package_config_overrides(self):
        from scripts.launcher.installation_dependencies import capture
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_project(root)
            user, global_config = root / 'selected-user.npmrc', root / 'selected-global.npmrc'
            for path in (user, global_config):
                path.write_bytes(b'')
            result = capture([sys.executable, '-c',
                              'import json, os; print(json.dumps([os.environ["NPM_CONFIG_USERCONFIG"], os.environ["NPM_CONFIG_GLOBALCONFIG"]]))'],
                             project, {'NPM_CONFIG_USERCONFIG': str(user),
                                       'NPM_CONFIG_GLOBALCONFIG': str(global_config)})
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), [str(user), str(global_config)])
            self.assertTrue(user.is_file() and global_config.is_file())

    def test_capture_timeout_has_safe_typed_details_without_command_or_output(self):
        from scripts.launcher import installation_dependencies as deps
        marker = 'fixture-sensitive-detail'
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            failure = subprocess.TimeoutExpired([f'https://private.invalid/{marker}'], 1800,
                                                output=marker, stderr=marker)
            with mock.patch.object(deps, 'controlled_run', side_effect=failure):
                with self.assertRaises(LauncherError) as caught:
                    deps.capture(['private-command'], project)
            self.assertIsInstance(caught.exception, deps.PackageTimeoutError)
            self.assertEqual(caught.exception.code, 'package_timeout')
            self.assertTrue(caught.exception.remedy)
            rendered = str(caught.exception) + caught.exception.remedy
            for private in (marker, 'private.invalid', 'private-command'):
                self.assertNotIn(private, rendered)

    @unittest.skipUnless(shutil.which('node'), 'A local Node executable is required for real npm tests')
    def test_real_npm_version_runs_with_isolated_capture_configuration(self):
        from scripts.launcher.installation_dependencies import capture
        from scripts.launcher.system_node import _npm_candidates
        node = Path(shutil.which('node')).resolve()
        cli = next((path for path in _npm_candidates(node) if path.is_file()), None)
        if cli is None:
            self.skipTest('An npm CLI beside local Node is required')
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            result = capture([node, cli, '--version'], project, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip(), r'^\d+\.\d+\.\d+$')


class AcquisitionFailureTests(unittest.TestCase):
    def test_package_failures_keep_safe_actionable_categories_without_diagnostics(self):
        from scripts.launcher import installation_dependencies as deps
        marker = 'fixture-sensitive-detail'
        cases = (
            ('CERTIFICATE_VERIFY_FAILED', 'package_tls_failed'),
            ('EPROTO SSL routines handshake failed', 'package_tls_failed'),
            ('TLS handshake failed', 'package_tls_failed'),
            ('npm ERR! code EINTEGRITY', 'package_integrity_failed'),
            ('THESE PACKAGES DO NOT MATCH THE HASHES', 'package_integrity_failed'),
            ('checksum verification failed', 'package_integrity_failed'),
            ('npm ERR! code ENOSPC', 'package_disk_full'),
            ('No space left on device', 'package_disk_full'),
            ('npm ERR! code EACCES', 'package_access_denied'),
            ('npm ERR! code EPERM', 'package_access_denied'),
            ('Access is denied', 'package_access_denied'),
            ('Unexpected tool failure', 'package_command_failed'),
        )
        for diagnostic, code in cases:
            with self.subTest(diagnostic=diagnostic):
                result = subprocess.CompletedProcess(['private-command'], 17,
                    f'https://upstream.invalid/private?token={marker}', f'{diagnostic} {marker}')
                with self.assertRaises(LauncherError) as caught:
                    deps._succeeded(result, 'private-stage')
                error = caught.exception
                self.assertIsInstance(error, deps.PackageCommandError)
                self.assertEqual(error.code, code)
                self.assertTrue(error.remedy)
                self.assertIn('17', str(error))
                rendered = str(error) + error.remedy
                for private in (marker, 'upstream.invalid', 'private-command', 'private-stage'):
                    self.assertNotIn(private, rendered)

    def test_package_failure_only_reports_positive_integer_exit_codes(self):
        from scripts.launcher import installation_dependencies as deps
        for returncode in (-17, True, 'fixture-sensitive-detail', None):
            with self.subTest(returncode=returncode):
                error = deps.PackageCommandError(subprocess.CompletedProcess([], returncode, '', ''))
                self.assertEqual(error.code, 'package_command_failed')
                self.assertNotIn('17', str(error))
                self.assertNotIn('fixture-sensitive-detail', str(error))

    def test_acquisition_cancellation_propagates_without_another_registry_attempt(self):
        from scripts.launcher import installation_dependencies as deps
        from scripts.launcher.process import OperationCancelled
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            with mock.patch.object(deps, '_npm_command', return_value=['npm']), \
                 mock.patch.object(deps, 'capture', side_effect=OperationCancelled('stopped')) as capture:
                with self.assertRaises(OperationCancelled):
                    deps._frontend_packages(project, SourceSettings(
                        npm_registry_url='https://selected.example/npm'), {}, root)
            self.assertEqual(capture.call_count, 1)

    def test_install_adds_system_trust_with_and_without_selected_ca(self):
        from scripts.launcher import installation_dependencies as dependencies

        roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        if not roots:
            self.skipTest('Requires a default trusted CA')
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            ca_file = Path(temporary) / 'corporate.pem'
            ca_file.write_text(ssl.DER_cert_to_PEM_cert(roots[0]), encoding='ascii')
            for selected in (None, ca_file):
                observed = []
                progress = []
                def packages(project, settings, tool_env, stage, *, cache_root=None):
                    bundle = Path(tool_env['NODE_EXTRA_CA_CERTS'])
                    self.assertTrue(bundle.is_file())
                    self.assertEqual(tool_env['PIP_CERT'], str(bundle))
                    self.assertNotEqual(bundle, ca_file)
                    self.assertEqual(tool_env['NPM_CONFIG_CAFILE'], str(bundle))
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.load_verify_locations(cafile=str(bundle))
                    self.assertTrue(set(roots).issubset(context.get_ca_certs(binary_form=True)))
                    observed.append(bundle)
                with self.subTest(selected=selected), \
                     mock.patch.object(dependencies, '_ensure_venv'), \
                     mock.patch.object(dependencies, 'dependency_stage', side_effect=lambda target, lock, install: install() or True), \
                     mock.patch('scripts.launcher.certificates._python_roots', return_value=ssl.DER_cert_to_PEM_cert(roots[0])), \
                     mock.patch.object(dependencies, '_python_packages', side_effect=packages), \
                     mock.patch.object(dependencies, '_frontend_packages', side_effect=packages):
                    import sys
                    dependencies.install_dependencies(project, SourceSettings(ca_file=selected, progress=progress.append),
                                                       {'AWCENTER_MANAGED_PYTHON': sys.executable})
                self.assertEqual(len(observed), 2)
                self.assertFalse(observed[0].exists())
                self.assertEqual(progress, ['Python sanal ortamı doğrulanıyor',
                    'Paket bağlantıları için güven deposu hazırlanıyor',
                    'Sistem sertifikaları hazırlanıyor',
                    *(['Seçilen ek sertifikalar hazırlanıyor'] if selected else []),
                    'Python/pip sertifikaları hazırlanıyor', 'Node.js sertifikaları hazırlanıyor',
                    'Birleşik sertifika dosyası hazırlanıyor',
                    'Python bağımlılıkları hazırlanıyor', 'Frontend bağımlılıkları hazırlanıyor'])

    def test_only_availability_failures_allow_package_source_fallback(self):
        from scripts.launcher.installation_dependencies import availability_failure

        for message in ("NewConnectionError: connection refused", "npm ERR! code ENOTFOUND",
                        "ReadTimeoutError", "HTTP error 404", "503 Service Unavailable"):
            with self.subTest(message=message):
                self.assertTrue(availability_failure(message))
        for message in ("CERTIFICATE_VERIFY_FAILED", "npm ERR! code EINTEGRITY",
                        "ERROR: Failed building wheel", "No space left on device",
                        "ERESOLVE unable to resolve dependency tree", "Access is denied"):
            with self.subTest(message=message):
                self.assertFalse(availability_failure(message))

    def test_explicit_transient_http_codes_allow_package_source_fallback(self):
        from scripts.launcher.installation_dependencies import availability_failure
        for code in (408, 429, 500, 502, 503, 504):
            for message in (f'npm ERR! code E{code}', f'HTTP error {code}'):
                with self.subTest(message=message):
                    self.assertTrue(availability_failure(message))
        for message in ('npm ERR! code E400', 'npm ERR! code E501', 'npm ERR! code E5030'):
            with self.subTest(message=message):
                self.assertFalse(availability_failure(message))

    def test_proxy_policy_rejection_allows_only_opted_in_package_fallback(self):
        from scripts.launcher.installation_dependencies import availability_failure
        for code in (401, 403, 407):
            message = f'ProxyError: Tunnel connection failed: {code} Forbidden'
            with self.subTest(code=code):
                self.assertTrue(availability_failure(message, restricted=True))
                self.assertFalse(availability_failure(message))

    def test_fatal_diagnostics_take_precedence_over_transient_codes(self):
        from scripts.launcher.installation_dependencies import availability_failure
        for fatal in ('CERTIFICATE_VERIFY_FAILED', 'TLS handshake failed', 'EPROTO SSL routines',
                      'EINTEGRITY', 'hash mismatch', 'checksum verification failed', 'DO NOT MATCH THE HASHES',
                      'Access is denied', 'EACCES', 'EPERM', 'No space left on device',
                      'ENOSPC', 'subprocess-exited-with-error'):
            with self.subTest(fatal=fatal):
                self.assertFalse(availability_failure(f'E503 E403 {fatal}', restricted=True))

    def test_package_names_and_paths_do_not_turn_network_failures_into_tls_errors(self):
        from scripts.launcher import installation_dependencies as deps
        for output in (
            'Collecting pyOpenSSL\nReadTimeoutError: connection timed out',
            'npm ERR! code E503\nGET https://registry.example/ssl-root-cas',
            r'npm ERR! path C:\Users\ssladmin\package\checksum\node_modules' + '\nE503',
            'Collecting checksum\nNewConnectionError: connection refused',
        ):
            with self.subTest(output=output):
                self.assertTrue(deps.availability_failure(output, restricted=True))
                error = deps.PackageCommandError(subprocess.CompletedProcess([], 1, output, ''))
                self.assertEqual(error.code, 'package_command_failed')

    def test_incidental_tls_or_checksum_names_do_not_override_access_errors(self):
        from scripts.launcher import installation_dependencies as deps
        for output in (
            r'npm ERR! path C:\Users\ssladmin\checksum\node_modules' + '\nnpm ERR! code EACCES',
            'Collecting pyOpenSSL\nnpm ERR! code EPERM',
            'GET https://registry.example/ssl-root-cas\nPermission denied',
        ):
            with self.subTest(output=output):
                self.assertFalse(deps.availability_failure(output, restricted=True))
                error = deps.PackageCommandError(subprocess.CompletedProcess([], 1, output, ''))
                self.assertEqual(error.code, 'package_access_denied')

    def test_real_tls_error_signatures_take_precedence_over_network_failures(self):
        from scripts.launcher import installation_dependencies as deps
        for diagnostic in (
            'SSLError: handshake failed', 'SSLCertVerificationError: verification failed',
            'CertificateError: hostname mismatch', 'CERTIFICATE_VERIFY_FAILED',
            'SSL certificate verification failed', 'TLS handshake failed',
            'SSL routines: wrong version number', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE',
            'DEPTH_ZERO_SELF_SIGNED_CERT', 'SELF_SIGNED_CERT_IN_CHAIN', 'CERT_HAS_EXPIRED',
            'CERT_NOT_YET_VALID', 'ERR_TLS_CERT_ALTNAME_INVALID',
        ):
            with self.subTest(diagnostic=diagnostic):
                output = f'E503 ReadTimeoutError\n{diagnostic}'
                self.assertFalse(deps.availability_failure(output, restricted=True))
                error = deps.PackageCommandError(subprocess.CompletedProcess([], 1, '', output))
                self.assertEqual(error.code, 'package_tls_failed')

    def test_selected_npm_acquisition_timeout_tries_public_in_isolated_stages(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            attempts = []
            def capture(command, *_, progress=None):
                if '--registry' in command:
                    registry = command[command.index('--registry') + 1]
                    tree = Path(command[command.index('--prefix') + 1])
                    self.assertEqual((tree / 'package-lock.json').read_text(), '{}')
                    attempts.append((registry, tree))
                    if 'selected.example' in registry:
                        (tree / 'package-lock.json').write_text('incomplete acquisition')
                        raise deps.PackageTimeoutError()
                return subprocess.CompletedProcess(command, 0, '', '')
            with mock.patch.object(deps, '_npm_command', return_value=['npm']), \
                 mock.patch.object(deps, 'capture', side_effect=capture):
                deps._frontend_packages(project, SourceSettings(mode='restricted',
                    npm_registry_url='https://selected.example/npm'), {}, root)
            self.assertEqual([registry for registry, _ in attempts],
                             ['https://selected.example/npm', 'https://registry.npmjs.org'])
            self.assertNotEqual(attempts[0][1], attempts[1][1])
            self.assertEqual((project.frontend / 'package-lock.json').read_text(), '{}')

    def test_all_npm_acquisition_timeouts_keep_safe_final_timeout(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            registries = []
            def capture(command, *_, progress=None):
                self.assertIn('--registry', command)
                registries.append(command[command.index('--registry') + 1])
                raise deps.PackageTimeoutError()
            with mock.patch.object(deps, '_npm_command', return_value=['npm']), \
                 mock.patch.object(deps, 'capture', side_effect=capture):
                with self.assertRaises(deps.PackageTimeoutError):
                    deps._frontend_packages(project, SourceSettings(mode='restricted',
                        npm_registry_url='https://selected.example/npm'), {}, root)
            self.assertEqual(registries, ['https://selected.example/npm', 'https://registry.npmjs.org'])

    def test_npm_acquisition_timeouts_can_use_a_verified_offline_fallback(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            offline = root / 'offline'
            (offline / 'npm-cache').mkdir(parents=True)
            (offline / 'npm-cache/fixture').write_bytes(b'immutable cache')
            commands = []
            def capture(command, *_, progress=None):
                commands.append(command)
                if '--registry' in command:
                    raise deps.PackageTimeoutError()
                cache = Path(command[command.index('--cache') + 1])
                self.assertEqual((cache / 'fixture').read_bytes(), b'immutable cache')
                (cache / 'npm-log').touch()
                return subprocess.CompletedProcess(command, 0, '', '')
            with mock.patch.object(deps, '_npm_command', return_value=['npm']), \
                 mock.patch.object(deps, '_offline_dependencies', side_effect=[None, offline]), \
                 mock.patch.object(deps, 'capture', side_effect=capture):
                deps._frontend_packages(project, SourceSettings(mode='restricted',
                    npm_registry_url='https://selected.example/npm'), {}, root)
            self.assertEqual(len(commands), 3)
            self.assertIn('--offline', commands[-1])
            self.assertFalse((offline / 'npm-cache/npm-log').exists())

    def test_final_npm_install_timeout_is_terminal_after_successful_acquisition(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            commands = []
            def capture(command, *_, progress=None):
                commands.append(command)
                if '--offline' in command:
                    raise deps.PackageTimeoutError()
                return subprocess.CompletedProcess(command, 0, '', '')
            with mock.patch.object(deps, '_npm_command', return_value=['npm']), \
                 mock.patch.object(deps, 'capture', side_effect=capture):
                with self.assertRaises(deps.PackageTimeoutError):
                    deps._frontend_packages(project, SourceSettings(mode='restricted',
                        npm_registry_url='https://selected.example/npm'), {}, root)
            self.assertEqual(len(commands), 2)
            self.assertIn('--offline', commands[-1])

    def test_pip_wheel_timeout_is_terminal_without_another_source_attempt(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            with mock.patch.object(deps, 'capture', side_effect=deps.PackageTimeoutError()) as capture:
                with self.assertRaises(deps.PackageTimeoutError):
                    deps._python_packages(project, SourceSettings(mode='restricted',
                        python_index_url='https://selected.example/simple'), {}, root)
            self.assertEqual(capture.call_count, 1)

    def test_verified_local_dependencies_prevent_network_in_every_mode(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            offline = root / 'offline'
            (offline / 'wheels').mkdir(parents=True)
            (offline / 'npm-cache').mkdir()
            for mode in ('online', 'restricted', 'corporate', 'offline'):
                stage = root / f'{mode}-stage'
                stage.mkdir()
                commands = []
                def capture(command, *_, progress=None):
                    commands.append(command)
                    self.assertNotIn('--index-url', command)
                    self.assertNotIn('--registry', command)
                    return subprocess.CompletedProcess(command, 0, '', '')
                with self.subTest(mode=mode), mock.patch.object(deps, '_offline_dependencies', return_value=offline), \
                     mock.patch.object(deps, '_npm_command', return_value=['npm']), \
                     mock.patch.object(deps, 'capture', side_effect=capture):
                    settings = SourceSettings(mode=mode, offline_dir=offline)
                    deps._python_packages(project, settings, {}, stage)
                    deps._frontend_packages(project, settings, {}, stage)
                self.assertEqual(len(commands), 3)
                self.assertIn('--no-index', commands[0])
                self.assertIn('--offline', commands[-1])

    def test_adjacent_dependency_manifest_is_verified_before_use(self):
        from scripts.launcher import installation_dependencies as deps
        from scripts.launcher.offline_manifest import artifact_metadata, lock_metadata, target_metadata
        from scripts.launcher.model import Scope
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            media = root / 'media'
            dependencies = media / 'dependencies'
            (dependencies / 'wheels').mkdir(parents=True)
            wheel = dependencies / 'wheels/reviewed.whl'
            wheel.write_bytes(b'reviewed wheel')
            manifest = {'format_version': 1, 'target': target_metadata(),
                        'locks': lock_metadata(project, Scope()), 'artifacts': artifact_metadata(dependencies)}
            (dependencies / 'manifest.json').write_text(json.dumps(manifest))
            settings = SourceSettings(runtime_dirs=(media,))
            self.assertEqual(deps._offline_dependencies(project, settings), dependencies)
            wheel.write_bytes(b'changed')
            with self.assertRaisesRegex(LauncherError, 'checksum'):
                deps._offline_dependencies(project, settings)

    def test_online_registry_rejection_tries_the_selected_registry(self):
        from scripts.launcher import installation_dependencies as deps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = create_project(root)
            (project.frontend / 'package-lock.json').write_text('{}')
            events = []
            registries = []
            def capture(command, *_, progress=None):
                if '--registry' in command:
                    self.assertTrue(events)
                    self.assertEqual(events[-1][0], 'progress')
                    registry = command[command.index('--registry') + 1]
                    registries.append(registry)
                    events.append(('attempt', registry))
                    if registry == 'https://registry.npmjs.org':
                        return subprocess.CompletedProcess(command, 1, '', 'npm ERR! code E403')
                return subprocess.CompletedProcess(command, 0, '', '')
            settings = SourceSettings(npm_registry_url='https://selected.example/npm',
                progress=lambda message: events.append(('progress', message)))
            with mock.patch.object(deps, '_npm_command', return_value=['npm']), \
                 mock.patch.object(deps, 'capture', side_effect=capture):
                deps._frontend_packages(project, settings, {}, root)
            self.assertEqual(registries, ['https://registry.npmjs.org', 'https://selected.example/npm'])
            self.assertFalse(any('https://' in message for kind, message in events if kind == 'progress'))

    def test_offline_npm_cache_is_copied_before_installation(self):
        from scripts.launcher.installation_dependencies import _frontend_packages

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_project(root)
            (project.frontend / "package-lock.json").write_text("{}", encoding="utf-8")
            offline = root / "offline"
            (offline / "npm-cache").mkdir(parents=True)
            (offline / "npm-cache" / "fixture").write_text("immutable", encoding="utf-8")
            stage = root / "stage"
            stage.mkdir()
            calls = []

            def capture(command, *_, progress=None):
                calls.append(command)
                if "--offline" not in command:
                    return subprocess.CompletedProcess(command, 1, "", "npm ERR! code ENOTFOUND")
                cache = Path(command[command.index("--cache") + 1])
                self.assertNotEqual(cache, offline / "npm-cache")
                (cache / "npm-log").write_text("mutable", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch("scripts.launcher.installation_dependencies._npm_command", return_value=["npm"]), \
                 mock.patch("scripts.launcher.installation_dependencies._offline_dependencies", return_value=offline), \
                 mock.patch("scripts.launcher.installation_dependencies.capture", side_effect=capture):
                _frontend_packages(project, SourceSettings(offline_dir=offline), {}, stage)
            self.assertEqual([path.name for path in (offline / "npm-cache").iterdir()], ["fixture"])
            self.assertEqual(len(calls), 1)

    def test_integrity_failure_does_not_try_another_registry(self):
        from scripts.launcher.installation_dependencies import _frontend_packages

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_project(root)
            (project.frontend / "package-lock.json").write_text("{}", encoding="utf-8")
            with mock.patch("scripts.launcher.installation_dependencies._npm_command", return_value=["npm"]), \
                 mock.patch("scripts.launcher.installation_dependencies.capture", return_value=
                            subprocess.CompletedProcess([], 1, "", "EINTEGRITY")) as capture:
                with self.assertRaises(LauncherError):
                    _frontend_packages(project, SourceSettings(npm_registry_url="https://mirror.example"), {}, root)
            self.assertEqual(capture.call_count, 1)


if __name__ == "__main__":
    unittest.main()
