"""Source and packaged Manager lifecycle acceptance on disposable Windows hosts."""
import hashlib
from contextlib import ExitStack
import json
import os
from pathlib import Path
import platform
import runpy
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import test_manager_package as fixtures
from scripts.manager_windows_acceptance import LiveAcceptance, StartupEvidence, acceptance_programs, deny_external_network


def acceptance_matrix(environment):
    profile = environment.get('AWCENTER_ACCEPTANCE_PROFILE', '')
    tools = environment.get('AWCENTER_ACCEPTANCE_TOOLS', '')
    if not profile and not tools:
        return ('dev', 'prod'), (True, False)
    if profile not in {'dev', 'prod'} or tools not in {'system', 'managed'}:
        raise ValueError('Native acceptance requires a valid profile and tool selection together')
    return (profile,), (tools == 'system',)


def record_sample(result, distribution, profile, tools, attempt):
    sample = dict(distribution=distribution, profile=profile, tools=tools, attempt=attempt,
                  windows=platform.version(), **result.summary())
    print('[native evidence] ' + json.dumps(sample), flush=True)
    destination = os.environ.get('AWCENTER_ACCEPTANCE_EVIDENCE')
    if destination:
        directory = Path(destination)
        directory.mkdir(parents=True, exist_ok=True)
        name = f'{distribution}-{profile}-{tools}-{attempt}.json'
        (directory / name).write_text(json.dumps(sample, indent=2), encoding='utf-8')


def prepared_outputs(source, profile):
    outputs = [source / folder / '.awcenter-packages.json' for folder in ('.venv', 'frontend/node_modules')]
    if profile == 'prod':
        outputs.append(source / 'frontend/dist/index.html')
    return [(hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns) for path in outputs]


def click_and_stop(source, environment, profile, *, password=None, executable=None, when_ready=None):
    """Drive real Tk buttons, private IPC and contained worker; intercept the browser handoff."""
    from scripts.manager.controller import ManagerController
    evidence = StartupEvidence()
    errors = []
    warm = password is None

    class DrivenController(ManagerController):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, browser_opener=evidence.open_browser)
            if self.view.variables['profile'].get() != profile:
                self.view.variables['profile'].set(profile)
            self.view.request_admin = lambda _id, send: send(
                {'username': 'U12345', 'password': password} if password else None)
            self.view.request_migration = lambda _id, send: send(False)
            self.view.confirm_stop = lambda: True
            self.root.mainloop = self.drive

        def _handle_event(self, event):
            task = self.tasks.get(event.get('task_id'))
            if task and task.action == 'ensure':
                evidence.observe(event)
            super()._handle_event(event)

        def wait_for(self, predicate, seconds):
            deadline = time.monotonic() + seconds
            while not predicate():
                if time.monotonic() >= deadline:
                    raise AssertionError('Timed out waiting for native desktop lifecycle')
                self.root.update()
                time.sleep(0.02)

        def drive(self):
            try:
                self.wait_for(lambda: not self.busy and self.view._profile_presentation()['status'] != 'inspecting', 300)
                assert self.view._profile_presentation()['status'] == ('stopped' if warm else 'not_installed')
                evidence.begin()
                self.view.action_buttons['start'].invoke()
                assert any(task.action == 'ensure' for task in self.tasks.values()), 'Primary action did not dispatch ensure'
                self.wait_for(lambda: evidence.browser_calls or evidence.failed, 1200 if warm else 3600)
                evidence.check(warm=warm)
                if when_ready:
                    when_ready(evidence.ready_url)
                self.view.banner_stop_button.invoke()
                self.wait_for(lambda: not any(task.active and task.action == 'ensure' for task in self.tasks.values()), 90)
                assert all(task.status == 'cancelled' for task in self.tasks.values() if task.action == 'ensure')
                evidence.check(warm=warm)
            except Exception as error:
                errors.append(error)
            finally:
                self.close()
                self.wait_for(lambda: self.closed, 90)

    from scripts.manager import main
    with ExitStack() as context:
        context.enter_context(patch.dict(os.environ, environment, clear=True))
        context.enter_context(patch('scripts.manager.controller.ManagerController', DrivenController))
        startup_error = context.enter_context(patch.object(main, '_startup_error'))
        preferences_warning = context.enter_context(patch.object(main, '_preferences_warning'))
        if executable:
            # Run this revision's Tk controller against the unmodified frozen worker.
            runtime = SimpleNamespace(frozen=True, executable=str(executable))
            context.enter_context(patch('scripts.manager.paths.sys', runtime))
            context.enter_context(patch('scripts.manager.transport.sys', runtime))
        entry = str(source / 'AWCenterManager.pyw')
        context.enter_context(patch.object(sys, 'argv', [entry, '--root', str(source)] if executable else [entry]))
        try:
            runpy.run_path(entry, run_name='__main__')
        except SystemExit as finished:
            result = finished.code
        else:
            raise AssertionError('The windowed entrypoint did not complete')
        if errors:
            raise errors[0]
        assert result == 0 and not startup_error.called and not preferences_warning.called
    return evidence


class ContainmentTests(unittest.TestCase):
    def test_startup_evidence_rejects_warm_preparation_even_after_successful_readiness(self):
        sample = StartupEvidence()
        sample.observe({'type': 'resources', 'action': 'provision', 'source_root': '/private/location'})
        sample.observe({'type': 'phase', 'message': 'Python paketleri: izinli kaynak 1/2 deneniyor'})
        sample.observe({'type': 'phase', 'message': 'some operator-supplied text'})
        sample.observe({'type': 'input', 'kind': 'admin', 'request_id': 'private-id'})
        sample.observe({'type': 'ready', 'url': 'http://private-host/'})
        sample.open_browser('http://private-host/')
        with self.assertRaises(AssertionError):
            sample.check(warm=True)
        summary = sample.summary()
        self.assertEqual(summary['locked_branches'], ['provision'])
        self.assertEqual(summary['source_attempts'], {'python_packages': 1, 'npm_packages': 0, 'runtime': 0})
        self.assertEqual(summary['prompts'], 1)
        self.assertNotIn('private', json.dumps(summary))
        self.assertNotIn('operator', json.dumps(summary))

    def test_warm_evidence_requires_locked_start_then_readiness_and_exactly_one_browser_call(self):
        sample = StartupEvidence()
        sample.observe({'type': 'resources', 'action': 'start'})
        sample.observe({'type': 'ready', 'url': 'http://127.0.0.1/app/'})
        sample.open_browser('http://127.0.0.1/app/')
        sample.check(warm=True)
        sample.open_browser('http://127.0.0.1/app/')
        with self.assertRaises(AssertionError):
            sample.check(warm=True)
        early = StartupEvidence()
        early.observe({'type': 'resources', 'action': 'start'})
        early.open_browser('http://127.0.0.1/app/')
        early.observe({'type': 'ready', 'url': 'http://127.0.0.1/app/'})
        with self.assertRaises(AssertionError):
            early.check(warm=True)

    def test_phase_timing_survives_interruption_without_exporting_worker_messages(self):
        sample = StartupEvidence()
        sample.begin(10.0)
        sample.observe({'type': 'phase', 'message': 'runtime hazırlığı'}, now=12.0)
        sample.observe({'type': 'phase', 'message': 'kilitli bağımlılıklar'}, now=15.0)
        sample.observe({'type': 'phase', 'message': 'operator text'}, now=16.0)
        sample.observe({'type': 'done', 'ok': True, 'cancelled': True}, now=18.5)
        self.assertEqual(sample.summary()['phase_ms'], {'planning': 2000, 'runtime': 3000, 'dependencies': 3500})
        self.assertIsNone(sample.summary()['click_to_browser_ms'])

    def test_default_acceptance_runs_all_four_cases_and_ci_selection_fails_closed(self):
        self.assertEqual(acceptance_matrix({}), (('dev', 'prod'), (True, False)))
        for profile in ('dev', 'prod'):
            for tools in ('system', 'managed'):
                self.assertEqual(acceptance_matrix({'AWCENTER_ACCEPTANCE_PROFILE': profile,
                    'AWCENTER_ACCEPTANCE_TOOLS': tools}), ((profile,), (tools == 'system',)))
        for values in ({'AWCENTER_ACCEPTANCE_PROFILE': 'dev'},
                       {'AWCENTER_ACCEPTANCE_TOOLS': 'managed'},
                       {'AWCENTER_ACCEPTANCE_PROFILE': 'unknown', 'AWCENTER_ACCEPTANCE_TOOLS': 'system'}):
            with self.assertRaises(ValueError):
                acceptance_matrix(values)

    def test_firewall_requires_explicit_programs_and_never_blocks_the_ci_host(self):
        with patch('scripts.manager_windows_acceptance.subprocess.run') as run:
            with self.assertRaises(ValueError), deny_external_network('10.0.0.10', []):
                pass
            run.assert_not_called()
            run.return_value = subprocess.CompletedProcess([], 0, b'', b'')
            programs = [Path('/test/manager.exe'), Path('/test/python.exe')]
            with self.assertRaisesRegex(RuntimeError, 'test failure'):
                with deny_external_network('10.0.0.10', programs):
                    raise RuntimeError('test failure')
            commands = [call.args[0] for call in run.call_args_list]
            adds = [command for command in commands if 'add' in command]
            deletes = [command for command in commands if 'delete' in command]
            self.assertEqual(len(adds), len(programs))
            self.assertEqual(len(deletes), len(programs))
            for command, program in zip(adds, programs):
                self.assertIn('program=' + str(program.resolve()), command)
                self.assertIn('action=block', command)
                self.assertIn(',::/1,8000::/1', command[-1])

    def test_containment_covers_future_system_managed_and_release_interpreters(self):
        from scripts.launcher.installation_sources import load_catalog
        from scripts.launcher.toolchain import _directory
        directory, source = Path('/acceptance'), Path('/acceptance/source')
        with patch('scripts.manager.payload.verify_source_payload', return_value={'fingerprint': 'a' * 64}):
            programs = acceptance_programs(Path('/bundle/Manager.exe'), directory, source,
                                           Path('/system/python.exe'), Path('/system/node.exe'))
        for path in ('/bundle/Manager.exe', '/system/python.exe', '/system/node.exe',
                     '/acceptance/source/.venv/Scripts/python.exe'):
            self.assertIn(Path(path), programs)
        home = directory / 'local/AWCenter'
        self.assertIn(home / 'releases' / ('a' * 64) / 'source/.venv/Scripts/python.exe', programs)
        self.assertIn(home / 'r' / ('a' * 12) / '.venv/Scripts/python.exe', programs)
        for name in ('python', 'node'):
            artifact = load_catalog()[name]
            self.assertIn(_directory(home, artifact) / artifact.executable, programs)

    def test_source_dev_containment_covers_checkout_without_a_distribution_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'checkout'
            programs = acceptance_programs(None, directory, source,
                                           Path('/system/python.exe'), Path('/system/node.exe'))
            self.assertIn(source / '.venv/Scripts/python.exe', programs)
            self.assertIn(Path('/system/node.exe'), programs)
            self.assertIn(Path('/system/python.exe'), programs)


@unittest.skipUnless(os.name == 'nt' and os.environ.get('AWCENTER_ACCEPTANCE_SOURCE_CHECKOUT'),
                     'Requires an explicitly disposable clean Windows checkout')
class NativeSourceAcceptance(unittest.TestCase):
    environment = fixtures.NativeWindowsPackageTests.environment

    def test_default_source_button_provisions_from_empty_cache_then_opens_offline(self):
        source = Path(__file__).resolve().parents[1]
        self.assertEqual(source, Path(os.environ['AWCENTER_ACCEPTANCE_SOURCE_CHECKOUT']).resolve())
        self.assertEqual(Path.cwd().resolve(), source)
        for path in (source / '.venv', source / '.runtime', source / 'frontend/node_modules',
                     source / 'frontend/dist', source / 'install-manifest.json', source.parent / 'install-manifest.json'):
            self.assertFalse(path.exists(), 'Source acceptance requires a clean checkout without offline media')
        python = Path(sys.executable).resolve()
        node = Path(shutil.which('node')).resolve()
        host = socket.gethostbyname(socket.gethostname())
        password = secrets.token_urlsafe(48)
        with tempfile.TemporaryDirectory(prefix='awc-source-') as temporary:
            directory = Path(temporary).resolve()
            environment = self.environment(directory, network=True)
            environment['PATH'] = os.pathsep.join((str(python.parent), str(node.parent), environment['PATH']))
            home = directory / 'local/AWCenter'
            self.assertFalse(home.exists())
            cold = click_and_stop(source, environment, 'dev', password=password)
            record_sample(cold, 'source', 'dev', 'automatic', 0)
            for kind, counter in (('python', 'python_packages'), ('npm', 'npm_packages')):
                self.assertGreater(cold.source_attempts[counter], 0)
                self.assertTrue(any((home / 'cache/packages' / kind).glob('*/manifest.json')))
            saved = json.loads((home / 'config/dev.profile.json').read_text(encoding='utf-8'))
            self.assertEqual(Path(saved['python_executable']).resolve(), python)
            self.assertEqual(Path(saved['node_executable']).resolve(), node)
            before = prepared_outputs(source, 'dev')
            programs = acceptance_programs(None, directory, source, python, node)
            with deny_external_network(host, programs):
                NativeOfflineAcceptance.assert_runtime_network_denied(self, saved, source, home)
                warm = click_and_stop(source, environment, 'dev', when_ready=lambda url: LiveAcceptance(
                    f"http://127.0.0.1:{saved['backend_port']}", frontend_origin=url.removesuffix('/app/')).exercise(password))
                record_sample(warm, 'source', 'dev', 'automatic', 1)
                self.assertEqual(prepared_outputs(source, 'dev'), before)


@unittest.skipUnless(os.name == 'nt' and os.environ.get('AWCENTER_RUN_MANAGER_WINDOWS_SMOKE') == '1',
                     'Requires the packaged native Windows acceptance job')
class NativeOfflineAcceptance(unittest.TestCase):
    setUp = fixtures.NativeWindowsPackageTests.setUp
    environment = fixtures.NativeWindowsPackageTests.environment
    stop_worker = staticmethod(fixtures.NativeWindowsPackageTests.stop_worker)
    next_event = fixtures.NativeWindowsPackageTests.next_event
    copy_clean_source = fixtures.NativeWindowsPackageTests.copy_clean_source
    provision_request = staticmethod(fixtures.NativeWindowsPackageTests.provision_request)

    def start_worker(self, *args, **kwargs):
        child, events = fixtures.NativeWindowsPackageTests.start_worker(self, *args, **kwargs)
        self.case_processes.callback(self.stop_worker, child)
        return child, events

    @classmethod
    def setUpClass(cls):
        cls.executable = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        from scripts.manager.distribution import verify_distribution
        assert verify_distribution(cls.executable.parent).get('complete') is True
        cls.node = shutil.which('node')
        assert cls.node, 'The system-tools matrix requires a compatible system Node'
        cls.python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()

    def certificate(self, directory, host):
        # Only this disposable test helper gets cryptography; no global install.
        libraries = directory / 'test-libraries'
        result = subprocess.run([str(self.python), '-m', 'pip', '--isolated', 'install', '--no-index',
            '--find-links', str(self.executable.parent / 'dependencies/wheels'), '--target', str(libraries),
            'cryptography'], capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, 'Offline TLS test fixture dependencies are incomplete')
        script = '''import datetime, ipaddress, pathlib, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
directory, host = pathlib.Path(sys.argv[1]), sys.argv[2]
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'AWC acceptance')])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1))
        .not_valid_after(now+datetime.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]), False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True).sign(key, hashes.SHA256()))
(directory/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(directory/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
'''
        result = subprocess.run([str(self.python), '-c', script, str(directory), host],
            env={**os.environ, 'PYTHONPATH': str(libraries)}, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, 'TLS fixture creation failed')
        from scripts.launcher.installation_permissions import secure_path
        for name in ('cert.pem', 'key.pem'):
            secure_path(directory / name)

    def run_until_ready(self, directory, request, password, evidence=None):
        child, events = self.start_worker(self.executable, directory, request, network=True)
        deadline = time.monotonic() + 1200
        admin = False
        while True:
            event = self.next_event(child, events, deadline)
            if evidence is not None:
                evidence.observe(event)
            self.assertFalse(password in json.dumps(event), 'Worker event exposed an administrator credential')
            if event['type'] == 'input':
                self.assertEqual(event.get('kind'), 'admin')
                self.assertFalse(admin, 'The first administrator was requested twice')
                admin = True
                child.stdin.write((json.dumps({'type': 'admin', 'value': {'username': 'U12345', 'password': password}}) + '\n').encode())
                child.stdin.flush()
            if event['type'] in {'error', 'done'}:
                self.fail('Native lifecycle ended before readiness: ' + event.get('code', 'worker_stopped'))
            if event['type'] == 'ready':
                return child, events, admin

    def stop_cleanly(self, child, events, host, ports):
        child.stdin.write(b'{"type":"cancel"}\n')
        child.stdin.flush()
        deadline = time.monotonic() + 90
        while True:
            event = self.next_event(child, events, deadline)
            if event['type'] == 'done':
                self.assertTrue(event['ok'])
                self.assertTrue(event['cancelled'])
                break
        child.wait(timeout=30)
        for port in ports:
            with socket.socket() as probe:
                probe.settimeout(1)
                self.assertNotEqual(probe.connect_ex((host, port)), 0)

    def assert_runtime_network_denied(self, saved, actual_source, home):
        from scripts.launcher.installation_sources import load_catalog
        from scripts.launcher.toolchain import _directory
        node = saved.get('node_executable')
        if not node:
            artifact = load_catalog()['node']
            node = _directory(home, artifact) / artifact.executable
        probes = (
            [str(actual_source / '.venv/Scripts/python.exe'), '-I', '-B', '-c',
             "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(int(s.connect_ex(('1.1.1.1',443)) == 0))"],
            [str(node), '-e', "const s=require('net').connect(443,'1.1.1.1'); s.on('connect',()=>process.exit(1)); s.on('error',()=>process.exit(0)); s.setTimeout(2000,()=>{s.destroy();process.exit(0)});"],
        )
        for command in probes:
            result = subprocess.run(command, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, 'Application runtime bypassed OS network denial')

    def assert_prepared_integrity(self, source, saved, home):
        # Report only source-relative filenames and fixed tool check labels,
        # never file contents, environment values or private profile fields.
        from scripts.manager.payload import SOURCE_MANIFEST, _source_inventory
        from scripts.launcher.toolchain import inspect_toolchain
        expected = json.loads((source / SOURCE_MANIFEST).read_text(encoding='utf-8'))['artifacts']
        expected = {entry['path']: entry for entry in expected}
        actual = {entry['path']: entry for entry in _source_inventory(source)}
        changed = sorted(name for name in expected.keys() | actual.keys()
                         if expected.get(name) != actual.get(name))
        self.assertEqual(changed, [], 'Prepared source inventory changed after normal use')
        options = {name: Path(saved[name]) for name in ('python_executable', 'node_executable') if saved.get(name)}
        checks = inspect_toolchain(home, **options)
        self.assertTrue(all(check['status'] == 'ready' for check in checks), checks)

    def test_dev_prod_system_and_managed_tools_with_real_network_denial(self):
        # Forced managed runs complement discovery's missing-tools unit tests.
        # A genuinely clean standard-user machine is also a release field gate.
        host = socket.gethostbyname(socket.gethostname())
        self.assertFalse(host.startswith('127.'), 'Production acceptance needs an assigned IPv4')
        profiles, tools = acceptance_matrix(os.environ)
        for profile in profiles:
            for system in tools:
                with self.subTest(profile=profile, system_tools=system), tempfile.TemporaryDirectory(prefix='awc-offline-') as temporary, ExitStack() as processes:
                    self.case_processes = processes
                    print(f'[native] offline profile={profile}, system_tools={system}', flush=True)
                    directory = Path(temporary).resolve()
                    source = self.copy_clean_source(self.executable, directory)
                    request = self.provision_request(source, 'offline')
                    request.update(action='ensure', profile=profile, offline_dir=str(self.executable.parent),
                                   install_python=not system, install_node=not system)
                    if profile == 'dev':
                        request.pop('backend_port', None)
                        request.pop('frontend_port', None)
                    if system:
                        request.update(python_command=str(self.python), node_command=self.node)
                    if profile == 'prod':
                        self.certificate(directory, host)
                        request.update(host=host, tls_cert_file=str(directory / 'cert.pem'), tls_key_file=str(directory / 'key.pem'))
                    password = secrets.token_urlsafe(48)
                    if profile == 'dev' and not system:
                        # Reproduce a checkout carrying a system-Python venv
                        # before the user selects the managed interpreter.
                        created = subprocess.run(
                            [str(self.python), '-m', 'venv', '--without-pip', str(source / '.venv')],
                            cwd=source, env=self.environment(directory, network=True),
                            capture_output=True, timeout=60,
                        )
                        self.assertEqual(created.returncode, 0, 'Synthetic prior venv could not be created')
                        (source / '.venv' / 'prior-environment.txt').write_text('preserve', encoding='utf-8')
                    programs = acceptance_programs(self.executable, directory, source, self.python, self.node)
                    with deny_external_network(host, programs):
                        for address in ('1.1.1.1', '8.8.8.8'):
                            with self.assertRaises(OSError):
                                socket.create_connection((address, 443), timeout=2)
                        if profile == 'dev' and not system:
                            partial_evidence = StartupEvidence()
                            partial, partial_events = self.start_worker(self.executable, directory, request, network=True)
                            deadline = time.monotonic() + 1200
                            while True:
                                event = self.next_event(partial, partial_events, deadline)
                                partial_evidence.observe(event)
                                self.assertNotIn(event['type'], {'error', 'done'})
                                # The worker waits for input here. Earlier phase messages
                                # race the next filesystem mutation on the CI host.
                                if event['type'] == 'input' and event.get('kind') == 'admin':
                                    break
                            partial.stdin.write(b'{"type":"cancel"}\n')
                            partial.stdin.flush()
                            while event['type'] != 'done':
                                event = self.next_event(partial, partial_events, deadline)
                                partial_evidence.observe(event)
                            self.assertTrue(event.get('cancelled'))
                            partial.wait(timeout=30)
                            before_resume = prepared_outputs(source, 'dev')
                            record_sample(partial_evidence, 'packaged-cancelled-worker', profile, 'managed', 0)
                        first = StartupEvidence()
                        child, events, admin = self.run_until_ready(directory, request, password, first)
                        distribution = 'packaged-resumed-worker' if profile == 'dev' and not system else 'packaged-first-worker'
                        record_sample(first, distribution, profile, 'system' if system else 'managed', 0)
                        self.assertTrue(admin)
                        if profile == 'dev' and not system:
                            self.assertEqual(prepared_outputs(source, 'dev'), before_resume,
                                             'Resume repeated an already verified dependency install')
                            preserved = list((source / '.runtime/venv-backups').rglob('prior-environment.txt'))
                            self.assertEqual(len(preserved), 1)
                            self.assertEqual(preserved[0].read_text(encoding='utf-8'), 'preserve')
                        private = directory / 'local/AWCenter'
                        saved = json.loads((private / 'config' / (profile + '.profile.json')).read_text(encoding='utf-8'))
                        origin = f"https://{host}:{saved['backend_port']}" if profile == 'prod' else f"http://127.0.0.1:{saved['backend_port']}"
                        certificate = directory / 'cert.pem' if profile == 'prod' else None
                        frontend = origin if profile == 'prod' else f"http://127.0.0.1:{saved['frontend_port']}"
                        job_id, digest = LiveAcceptance(origin, certificate, frontend).exercise(password)
                        private = directory / 'local/AWCenter'
                        saved = json.loads((private / 'config' / (profile + '.profile.json')).read_text(encoding='utf-8'))
                        self.assertEqual(bool(saved.get('python_executable')), system)
                        self.assertEqual(bool(saved.get('node_executable')), system)
                        duplicate, duplicate_events = self.start_worker(self.executable, directory,
                            {**request, 'action': 'start'}, network=True)
                        deadline = time.monotonic() + 30
                        while True:
                            event = self.next_event(duplicate, duplicate_events, deadline)
                            self.assertNotEqual(event['type'], 'ready')
                            if event['type'] == 'done':
                                self.assertFalse(event['ok'])
                                break
                        duplicate.wait(timeout=30)
                        actual_source = Path(saved['source_root'])
                        self.assert_runtime_network_denied(saved, actual_source, private)
                        # Match AWCenter.cmd's immutable-runtime startup policy.
                        # A bare interpreter would itself create stdlib .pyc
                        # files before the CLI can reject the competing lease.
                        cli = subprocess.run([str(actual_source / '.venv/Scripts/python.exe'), '-B', '-X', 'utf8',
                            str(actual_source / 'launcher.py'), 'start', '--profile', profile],
                            cwd=actual_source, env=self.environment(directory, network=True),
                            capture_output=True, timeout=30)
                        self.assertNotEqual(cli.returncode, 0, 'CLI bypassed the live profile lease')
                        self.assertTrue('Başka bir işlem' in cli.stderr.decode('utf-8'),
                                        'CLI did not reject the live profile lease')
                        env = private / 'config' / (profile + '.env')
                        identity = hashlib.sha256(env.read_bytes()).hexdigest()
                        ports = [saved['backend_port']] + ([saved['frontend_port']] if profile == 'dev' else [])
                        bind = host if profile == 'prod' else '127.0.0.1'
                        self.stop_cleanly(child, events, bind, ports)
                        self.assert_prepared_integrity(actual_source, saved, private)
                        request['action'] = 'ensure'
                        if profile == 'prod' and not system:
                            child, events, admin = self.run_until_ready(directory, request, password)
                            self.stop_worker(child)  # Abrupt owner death must reap the entire tree.
                            child, events, admin = self.run_until_ready(directory, request, password)
                            self.assertFalse(admin)
                            self.assertEqual(hashlib.sha256(env.read_bytes()).hexdigest(), identity)
                            self.stop_cleanly(child, events, bind, ports)
                        def verify_persisted_output(url):
                            self.assertEqual(url, frontend + '/app/')
                            live = LiveAcceptance(origin, certificate, frontend)
                            live.exercise(password)
                            with live.request('/api/jobs/' + job_id + '/download/') as response:
                                self.assertEqual(hashlib.sha256(response.read()).hexdigest(), digest)

                        before = prepared_outputs(actual_source, profile)
                        for attempt in range(1, 4):
                            result = click_and_stop(source, self.environment(directory, network=True), profile,
                                executable=self.executable, when_ready=verify_persisted_output if attempt == 1 else None)
                            record_sample(result, 'packaged', profile, 'system' if system else 'managed', attempt)
                            self.assertEqual(prepared_outputs(actual_source, profile), before)
                            self.assertEqual(hashlib.sha256(env.read_bytes()).hexdigest(), identity)
                            for port in ports:
                                with socket.socket() as probe:
                                    probe.settimeout(1)
                                    self.assertNotEqual(probe.connect_ex((bind, port)), 0)
