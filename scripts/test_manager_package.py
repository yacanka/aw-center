"""Portable package build contracts and opt-in native Windows acceptance."""
from __future__ import annotations

import hashlib
import faulthandler
import importlib
import json
import os
from pathlib import Path
import queue
import runpy
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

from scripts.launcher.installation_sources import Artifact, SourceSettings
from scripts.launcher.model import LauncherError

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_spec_ships_certificate_exporter_at_the_external_probe_path(self):
        observed = {}
        def analysis(*args, **kwargs):
            observed.update(kwargs)
            return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=kwargs['datas'])
        with patch.dict(os.environ, {'AWCENTER_MANAGER_SOURCE': str(ROOT)}):
            runpy.run_path(str(ROOT / 'packaging/manager.spec'), init_globals={
                'Analysis': analysis, 'PYZ': lambda *a, **k: None,
                'EXE': lambda *a, **k: None, 'COLLECT': lambda *a, **k: None})
        source = ROOT / 'scripts/launcher/certificate_store.py'
        self.assertIn((str(source), 'scripts/launcher'), observed['datas'])
        self.assertTrue(source.is_file())
        # The file is executed by an external Python, independently of the
        # frozen module archive and without application packages on sys.path.
        isolated = self.root / 'scripts/launcher'
        isolated.mkdir(parents=True)
        shutil.copy2(source, isolated / source.name)
        result = subprocess.run([sys.executable, '-I', '-B', '-c',
            'import runpy,sys; c=runpy.run_path(sys.argv[1])["export_context"](); '
            'assert isinstance(c.get_ca_certs(binary_form=True), list)', str(isolated / source.name)],
            capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def setUp(self):
        try:
            self.builder = importlib.import_module('scripts.build_manager')
        except ModuleNotFoundError:
            self.fail('Portable desktop-manager packaging is not implemented')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_builder_refuses_non_windows_before_output_or_dependency_mutations(self):
        output = self.root / 'manager.zip'
        with patch.object(self.builder.sys, 'platform', 'darwin'):
            with self.assertRaises(LauncherError):
                self.builder.build_manager(ROOT, output, SourceSettings())
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_runtime_payload_is_exact_reviewed_catalog_with_corruption_rejection(self):
        artifacts = {}
        for name in ('python', 'node', 'npm'):
            data = (name + '-reviewed').encode()
            archive = self.root / (name + '.zip')
            archive.write_bytes(data)
            artifacts[name] = Artifact(name, '1.0', archive.name, 'https://example.invalid/' + archive.name,
                                       hashlib.sha256(data).hexdigest(), 'zip', name + '.exe')
        target = self.root / 'runtimes'
        with patch.object(self.builder, 'load_catalog', return_value=artifacts), \
             patch.object(self.builder, 'fetch_artifact', side_effect=lambda artifact, cache, settings: self.root / artifact.filename):
            metadata = self.builder.prepare_runtime_payload(target, SourceSettings())
        self.assertEqual(set(metadata), {'python', 'node', 'npm'})
        self.assertEqual(set(path.name for path in target.iterdir()), {value.filename for value in artifacts.values()})
        (target / 'python.zip').write_bytes(b'tampered')
        with patch.object(self.builder, 'load_catalog', return_value=artifacts):
            with self.assertRaises(LauncherError):
                self.builder.verify_runtime_payload(target, metadata)

    def test_portable_zip_inventory_covers_every_byte_without_local_paths(self):
        source = self.root / 'portable'
        (source / '_internal').mkdir(parents=True)
        (source / 'AWCenterManager.exe').write_bytes(b'Windows executable fixture')
        (source / '_internal/python311.dll').write_bytes(b'embedded Python fixture')
        (source / 'source').mkdir()
        (source / 'source/launcher.py').write_text('# fixture', encoding='utf-8')
        (source / 'runtimes').mkdir()
        output = self.root / 'AWCenterManager-windows-x64.zip'
        self.builder.write_portable_archive(source, output, {'source_fingerprint': 'a' * 64, 'runtimes': {}})
        checksum = output.with_suffix(output.suffix + '.sha256')
        self.assertEqual(checksum.read_text(encoding='ascii').split()[0], hashlib.sha256(output.read_bytes()).hexdigest())
        with zipfile.ZipFile(output) as archive:
            manifest = json.loads(archive.read('manager-manifest.json'))
            inventory = manifest['artifacts']
            self.assertEqual(set(archive.namelist()), {entry['path'] for entry in inventory} | {'manager-manifest.json'})
            for entry in inventory:
                data = archive.read(entry['path'])
                self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(entry['size'], len(data))
            self.assertNotIn(str(self.root), json.dumps(manifest))

    def test_package_never_overwrites_an_existing_archive_or_checksum(self):
        source = self.root / 'portable'
        source.mkdir()
        output = self.root / 'manager.zip'
        for preexisting in (output, output.with_suffix('.zip.sha256')):
            with self.subTest(preexisting=preexisting.name):
                preexisting.write_text('existing', encoding='utf-8')
                with self.assertRaises(LauncherError):
                    self.builder.write_portable_archive(source, output, {})
                self.assertEqual(preexisting.read_text(encoding='utf-8'), 'existing')
                preexisting.unlink()

    def test_spec_is_windowed_onedir_and_only_build_requirements_include_pyinstaller(self):
        spec = (ROOT / 'packaging/manager.spec').read_text(encoding='utf-8')
        self.assertIn('console=False', spec)
        self.assertIn('exclude_binaries=True', spec)
        self.assertIn("contents_directory='_internal'", spec)
        self.assertIn('COLLECT(', spec)
        self.assertIn('child_bootstrap.py', spec)
        self.assertIn('installation_catalog.json', spec)
        self.assertIn('PyInstaller==6.22.3', (ROOT / 'packaging/manager-requirements.txt').read_text(encoding='utf-8'))
        for path in ('requirements.in', 'requirements.txt'):
            self.assertNotIn('pyinstaller', (ROOT / path).read_text(encoding='utf-8').casefold())

    def test_windows_workflow_builds_and_runs_native_smoke_using_cmd(self):
        workflow = (ROOT / '.github/workflows/manager-windows.yml').read_text(encoding='utf-8')
        self.assertIn('runs-on: windows-latest', workflow)
        self.assertIn('shell: cmd', workflow)
        self.assertNotIn('pwsh', workflow.casefold())
        self.assertNotIn('powershell', workflow.casefold())
        self.assertIn('scripts/build_manager.py', workflow)
        self.assertIn('AWCENTER_RUN_MANAGER_WINDOWS_SMOKE', workflow)
        self.assertIn('scripts.test_manager_package', workflow)


@unittest.skipUnless(os.name == 'nt' and os.environ.get('AWCENTER_RUN_MANAGER_WINDOWS_SMOKE') == '1',
                     'Native packaged Windows acceptance requires AWCENTER_RUN_MANAGER_WINDOWS_SMOKE=1')
class NativeWindowsPackageTests(unittest.TestCase):
    def setUp(self):
        # Stack locations contain no request payloads and expose blocked cleanup
        # as well as slow provisioning when the runner reconnects after denial.
        faulthandler.dump_traceback_later(300, repeat=True)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)

    def environment(self, directory, *, network, python_on_path=None):
        system = Path(os.environ['SystemRoot'])
        values = {**os.environ, 'PATH': os.pathsep.join((str(system / 'System32'), str(system))),
                  'LOCALAPPDATA': str(directory / 'local'), 'PYTHONDONTWRITEBYTECODE': '1'}
        # A clean host must not inherit an application's existing environment,
        # administrator credentials, developer Python, Node or package settings.
        prefixes = ('AWCENTER_', 'DJANGO_', 'PIP_', 'NPM_CONFIG_', 'PYTHON', 'NODE_')
        values = {key: value for key, value in values.items() if not key.upper().startswith(prefixes)}
        if not network:
            values.update(HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9',
                          ALL_PROXY='http://127.0.0.1:9')
        for name in ('python', 'node', 'npm', 'git'):
            self.assertIsNone(shutil.which(name, path=values['PATH']), name)
        if python_on_path is not None:
            # Exclude the Windows py launcher too, so automatic discovery must
            # reach the one operator interpreter explicitly exposed by this test.
            values['PATH'] = str(python_on_path.parent)
            selected = shutil.which('python', path=values['PATH'])
            self.assertIsNotNone(selected, 'Controlled PATH must expose the operator Python')
            self.assertEqual(Path(selected).resolve(), python_on_path)
            self.assertIsNone(shutil.which('py', path=values['PATH']))
        return values

    def start_worker(self, executable, directory, request, *, network, python_on_path=None):
        from scripts.launcher.windows_job import WindowsJob
        child = subprocess.Popen([str(executable), '--manager-worker', '--manager-gate'],
                                 cwd=directory, env=self.environment(directory, network=network,
                                                                    python_on_path=python_on_path),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        child._launcher_job = WindowsJob(child._handle)
        self.addCleanup(self.stop_worker, child)
        child.stdin.write(b'go\n' + (json.dumps(request) + '\n').encode('utf-8'))
        child.stdin.flush()
        events = queue.Queue()
        def read_events():
            try:
                for line in iter(child.stdout.readline, b''):
                    events.put(json.loads(line))
            except Exception:
                events.put({'type': 'invalid'})
            finally:
                events.put(None)
        threading.Thread(target=read_events, daemon=True).start()
        return child, events

    @staticmethod
    def stop_worker(child):
        from scripts.launcher.process import terminate
        terminate([child])
        for stream in (child.stdin, child.stdout):
            if stream:
                stream.close()

    def next_event(self, child, events, deadline):
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=1)
                self.assertIsNotNone(event, 'Packaged worker exited before its completion event')
                self.assertIn(event.get('type'), {'phase', 'status', 'checks', 'ready', 'error', 'input', 'done', 'health', 'profile'})
                if event['type'] in {'phase', 'ready', 'error', 'done'}:
                    # Never print message, input, environment or process output.
                    print(f"[native] {event['type']}; {max(0, int(deadline - time.monotonic()))}s remaining", flush=True)
                return event
            except queue.Empty:
                self.assertIsNone(child.poll(), 'Packaged worker exited without a structured result')
        self.fail('Packaged worker acceptance timed out')

    def test_first_real_window_opens_without_installed_tools_or_network(self):
        executable = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        with tempfile.TemporaryDirectory(prefix='awcenter-manager-window-') as temporary:
            directory = Path(temporary).resolve()
            result_path = directory / 'window.json'
            environment = self.environment(directory, network=False)
            process = subprocess.run([str(executable), '--smoke-test', str(result_path)], cwd=directory,
                                     env=environment, capture_output=True, timeout=60, check=False)
            self.assertEqual(process.returncode, 0)
            result = json.loads(result_path.read_text(encoding='utf-8'))
            self.assertIs(result['ready'], True)
            self.assertFalse((directory / 'local').exists(), 'Opening a window must not provision a runtime')

    def test_packaged_worker_checks_all_source_modes_without_installing_tools(self):
        executable = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        for mode in ('offline', 'restricted', 'corporate', 'online'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix='awcenter-manager-source-') as temporary:
                directory = Path(temporary).resolve()
                request = {'action': 'test-sources', 'source_root': str(executable.parent / 'source'),
                           'profile': 'dev', 'source_mode': mode}
                child, events = self.start_worker(executable, directory, request, network=False)
                received = []
                deadline = time.monotonic() + 60
                while not received or received[-1]['type'] != 'done':
                    received.append(self.next_event(child, events, deadline))
                self.assertTrue(received[-1]['ok'], received)
                self.assertTrue(any(event['type'] == 'checks' for event in received))
                child.wait(timeout=15)
                self.assertEqual(child.returncode, 0)
                self.assertFalse((directory / 'local').exists(), 'Source checks must not install runtimes')

    def copy_clean_source(self, executable, directory):
        from scripts.manager.payload import _copy_verified_source, verify_source_payload
        original = executable.parent / 'source'
        target = directory / 'source'
        _copy_verified_source(original, target, verify_source_payload(original))
        return target

    @staticmethod
    def provision_request(source, mode):
        def unused_port():
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                return listener.getsockname()[1]
        backend, frontend = unused_port(), unused_port()
        while frontend == backend:
            frontend = unused_port()
        return {'action': 'provision', 'source_root': str(source),
                'profile': 'dev', 'source_mode': mode,
                'install_python': True,
                'backend_port': backend, 'frontend_port': frontend}

    def exercise_lifecycle(self, executable, directory, request, *, network, timeout):
        child, events = self.start_worker(executable, directory, request, network=network)
        try:
            return self._exercise_started_lifecycle(child, events, request, timeout)
        finally:
            # Clean up before TemporaryDirectory, including assertion failures.
            self.stop_worker(child)

    def _exercise_started_lifecycle(self, child, events, request, timeout):
        password = secrets.token_urlsafe(48)
        received, ready, admin_requested = [], False, False
        deadline = time.monotonic() + timeout
        while not received or received[-1]['type'] != 'done':
            event = self.next_event(child, events, deadline)
            received.append(event)
            if event['type'] == 'input':
                self.assertEqual(event.get('kind'), 'admin')
                admin_requested = True
                child.stdin.write((json.dumps({'type': 'admin', 'value': {
                    'username': 'U12345', 'password': password}}) + '\n').encode('utf-8'))
                child.stdin.flush()
            if event['type'] == 'ready':
                ready = True
                from urllib.request import ProxyHandler, build_opener
                # Dev serves its frontend from Vite; Django's deployment
                # readiness requires a production frontend artifact.
                for url in (f"http://127.0.0.1:{request['backend_port']}/health/live/",
                            f"http://127.0.0.1:{request['frontend_port']}/app/"):
                    with build_opener(ProxyHandler({})).open(url, timeout=15) as response:
                        self.assertEqual(response.status, 200)
                child.stdin.write(b'{"type":"cancel"}\n')
                child.stdin.flush()
        self.assertTrue(ready, received)
        self.assertTrue(received[-1]['ok'], received)
        self.assertTrue(received[-1].get('cancelled'), received)
        self.assertNotIn(password, json.dumps(received))
        child.wait(timeout=30)
        self.assertEqual(child.returncode, 0)
        for port in (request['backend_port'], request['frontend_port']):
            with socket.socket() as probe:
                probe.settimeout(2)
                self.assertNotEqual(probe.connect_ex(('127.0.0.1', port)), 0,
                                    'Stop must reap frontend/backend descendants')
        return admin_requested

    def test_real_packaged_online_provision_first_admin_readiness_and_stop(self):
        """Cold install, private admin pipe, readiness, stop and prepared restart."""
        executable = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        with tempfile.TemporaryDirectory(prefix='awcenter-manager-provision-') as temporary:
            directory = Path(temporary).resolve()
            source = self.copy_clean_source(executable, directory)
            request = self.provision_request(source, 'online')
            self.assertTrue(self.exercise_lifecycle(executable, directory, request, network=True, timeout=2400),
                            'A fresh packaged install must request its first administrator')
            private_env = directory / 'local/AWCenter/config/dev.env'
            before = hashlib.sha256(private_env.read_bytes()).digest()
            request['action'] = 'start'
            self.assertFalse(self.exercise_lifecycle(executable, directory, request, network=False, timeout=180),
                             'Prepared start must preserve the existing administrator')
            self.assertEqual(hashlib.sha256(private_env.read_bytes()).digest(), before,
                             'Prepared restart must not rewrite private keys or configuration')

    def test_real_packaged_system_python_provision_restart_and_automatic_discovery(self):
        """Use the host CPython through the frozen worker without installing Python."""
        executable = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        with tempfile.TemporaryDirectory(prefix='awcenter-manager-system-python-') as temporary:
            directory = Path(temporary).resolve()
            source = self.copy_clean_source(executable, directory)
            request = self.provision_request(source, 'online')
            request.update(install_python=False, python_command=str(python))
            self.assertTrue(self.exercise_lifecycle(executable, directory, request, network=True, timeout=2400),
                            'A fresh system-Python install must request its first administrator')
            home = directory / 'local/AWCenter'
            profile = json.loads((home / 'config/dev.profile.json').read_text(encoding='utf-8'))
            self.assertEqual(Path(profile['python_executable']).resolve(), python)
            base = subprocess.run([str(source / '.venv/Scripts/python.exe'), '-I', '-B', '-c',
                                   'import sys; print(sys._base_executable)'],
                                  cwd=source, env=self.environment(directory, network=False),
                                  capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(base.returncode, 0)
            self.assertEqual(Path(base.stdout.strip()).resolve(), python)
            self.assertEqual(list((home / 'runtimes').glob('python-*')), [],
                             'System selection must not install a managed Python runtime')
            private_env = home / 'config/dev.env'
            before = hashlib.sha256(private_env.read_bytes()).digest()
            request['action'] = 'start'
            self.assertFalse(self.exercise_lifecycle(executable, directory, request, network=False, timeout=180),
                             'Prepared system-Python start must preserve the existing administrator')
            self.assertEqual(hashlib.sha256(private_env.read_bytes()).digest(), before)

            inspection = {'action': 'inspect', 'source_root': str(source), 'profile': 'dev'}
            child, events = self.start_worker(executable, directory, inspection, network=False)
            received = []
            deadline = time.monotonic() + 180
            while not received or received[-1]['type'] != 'done':
                received.append(self.next_event(child, events, deadline))
            self.assertTrue(received[-1]['ok'], received)
            status = next(event for event in received if event['type'] == 'profile')
            self.assertEqual(status['status'], 'stopped')
            self.assertIn('sistem kurulumu', status['tools'])
            child.wait(timeout=30)
            self.assertEqual(list((home / 'runtimes').glob('python-*')), [])

    def test_real_packaged_cold_offline_provision_without_network(self):
        executable = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        bundle = executable.parent
        with tempfile.TemporaryDirectory(prefix='awcenter-manager-offline-') as temporary:
            directory = Path(temporary).resolve()
            source = self.copy_clean_source(executable, directory)
            request = self.provision_request(source, 'offline')
            request['offline_dir'] = str(bundle)
            self.assertTrue(self.exercise_lifecycle(executable, directory, request, network=False, timeout=2400),
                            'Cold offline install must create its first administrator')


if __name__ == '__main__':
    unittest.main()
