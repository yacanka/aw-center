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


def _wait(root, predicate, timeout):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        root.update()
        time.sleep(.025)
    if not predicate():
        raise AssertionError('Timed out waiting for the Manager action')


def drive_form(case, source, environment, profile, *, cold, password, values,
               executable=None, when_ready=None):
    """Drive the public entry and real Tk actions, intercepting only operator input/browser."""
    from scripts.manager import main, profile_window
    results = {'actions': [], 'prompts': 0, 'browser_calls': 0}
    failures = []

    class DrivenWindow(profile_window.ProfileWindow):
        def __init__(self, root, project):
            super().__init__(root, project)
            case.assertEqual(self.source.resolve(), source.resolve())
            root.mainloop = self.drive

        def _prompt_admin(self, reply):
            results['prompts'] += 1
            reply.put(('U12345', password) if cold and results['prompts'] == 1 else None)

        def _browser(self):
            case.assertTrue(self.ready_url)
            results['browser_calls'] += 1

        def click(self, action, timeout=300, *, allow_failure=False):
            results['actions'].append(action)
            self.buttons[action].invoke()
            case.assertIsNotNone(self.task, f'{action} button did not dispatch')
            _wait(self.root, lambda: self.task is None, timeout)
            if not allow_failure:
                case.assertFalse(self.last_error, self.last_error)
            return self.log.get('1.0', 'end')

        def drive(self):
            try:
                case.assertIsNone(self.task, 'Opening a saved profile auto-started a worker')
                if cold:
                    case.assertIsNone(self.profile)
                    self.buttons[profile].invoke()
                    for key, value in values.items():
                        self.variables[key].set(value)
                    self._resource_mode()
                    self.set_env(self.variables['env_file'].get())
                    # An absent runtime is itself a meaningful pre-install check result.
                    report = self.click('check', allow_failure=True)
                    case.assertTrue('eksik' in report.casefold() or 'bulunamadı' in report.casefold())
                    self.click('install', timeout=3600)
                    report = self.click('check')
                    case.assertIn('Python · kilitli paketler kurulu.', report)
                    case.assertIn('Frontend · kilitli paketler kurulu.', report)
                    if profile == 'prod':
                        self.click('tls')
                        self.click('build', timeout=1800)
                        case.assertTrue(Path(values['tls_cert_file']).is_file())
                        case.assertTrue((source / 'frontend/dist/index.html').is_file())
                case.assertEqual(self.profile, profile)
                self.buttons['run'].invoke()
                results['actions'].append('run')
                _wait(self.root, lambda: bool(self.ready_url) or self.task is None, 1800)
                case.assertTrue(self.ready_url, self.last_error or self.status.get())
                case.assertEqual(results['prompts'], int(cold))
                case.assertEqual(results['browser_calls'], 1)
                if when_ready:
                    when_ready(self.ready_url)
                self.buttons['stop'].invoke()
                _wait(self.root, lambda: self.task is None, 90)
                case.assertFalse(self.last_error, self.last_error)
                results['actions'].append('stop')
            except Exception as error:
                failures.append(error)
            finally:
                if self.task:
                    self.stop()
                    _wait(self.root, lambda: self.task is None, 90)
                self.close()

    with ExitStack() as context:
        context.enter_context(patch.dict(os.environ, environment, clear=True))
        context.enter_context(patch('scripts.manager.paths.worker_directory', return_value=source))
        context.enter_context(patch('scripts.manager.transport.worker_directory', return_value=source))
        if executable:
            runtime = SimpleNamespace(frozen=True, executable=str(executable))
            context.enter_context(patch('scripts.manager.transport.sys', runtime))
        context.enter_context(patch.object(profile_window, 'ProfileWindow', DrivenWindow))
        context.enter_context(patch.object(profile_window.messagebox, 'askokcancel', return_value=True))
        startup_error = context.enter_context(patch.object(main, '_startup_error'))
        entry = str(source / 'AWCenterManager.pyw')
        context.enter_context(patch.object(sys, 'argv', [entry]))
        try:
            runpy.run_path(entry, run_name='__main__')
        except SystemExit as finished:
            exit_code = finished.code
        else:
            raise AssertionError('The windowed entrypoint did not complete')
        if failures:
            raise failures[0]
        case.assertEqual(exit_code, 0)
        startup_error.assert_not_called()
    return results


def record_sample(sample, distribution, profile, tools, attempt):
    sample = dict(distribution=distribution, profile=profile, tools=tools, attempt=attempt,
                  windows=platform.version(), **sample)
    print('[native evidence] ' + json.dumps(sample), flush=True)
    destination = os.environ.get('AWCENTER_ACCEPTANCE_EVIDENCE')
    if destination:
        directory = Path(destination)
        directory.mkdir(parents=True, exist_ok=True)
        name = f'{distribution}-{profile}-{tools}-{attempt}.json'
        (directory / name).write_text(json.dumps(sample, indent=2), encoding='utf-8')


class ContainmentTests(unittest.TestCase):
    def test_fast_production_warm_evidence_requires_one_canonical_source_inventory(self):
        from scripts.launcher.startup_metrics import count_startup_work, startup_work
        sample = StartupEvidence(validation_policy='developer', profile='prod')
        sample.observe({'type': 'resources', 'action': 'start'})
        with startup_work(sample.observe, 'developer'):
            count_startup_work('source_inventory')
        sample.observe({'type': 'ready', 'url': 'https://192.0.2.1/app/'})
        sample.open_browser('https://192.0.2.1/app/')
        sample.check(warm=True)
        for counter, wrong in (('source_inventory', 0), ('source_inventory', 2), ('dependency_inventory', 1)):
            with self.subTest(counter=counter, count=wrong), patch.dict(sample.work_counts, {counter: wrong}):
                with self.assertRaises(AssertionError):
                    sample.check(warm=True)

    def test_developer_warm_evidence_requires_zero_actual_inventory_counts(self):
        from scripts.launcher.startup_metrics import startup_work
        sample = StartupEvidence(validation_policy='developer')
        sample.observe({'type': 'resources', 'action': 'start'})
        with startup_work(sample.observe, 'developer'):
            pass
        sample.observe({'type': 'ready', 'url': 'http://127.0.0.1/app/'})
        sample.open_browser('http://127.0.0.1/app/')
        sample.check(warm=True)
        self.assertEqual(sample.summary()['validation_policy'], 'developer')
        self.assertFalse(any(sample.summary()['work_counts'].values()))
        for operation in sample.summary()['work_counts']:
            with self.subTest(operation=operation):
                sample.work_counts[operation] = 1
                with self.assertRaises(AssertionError):
                    sample.check(warm=True)
                sample.work_counts[operation] = 0

    def test_developer_evidence_does_not_invent_zero_counts_without_a_worker_sample(self):
        sample = StartupEvidence(validation_policy='developer')
        sample.observe({'type': 'resources', 'action': 'start'})
        sample.observe({'type': 'ready', 'url': 'http://127.0.0.1/app/'})
        sample.open_browser('http://127.0.0.1/app/')
        with self.assertRaises(AssertionError):
            sample.check(warm=True)

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


def connection_inputs(profile, host):
    bind = host if profile == 'prod' else '127.0.0.1'
    with socket.socket() as backend, socket.socket() as frontend:
        backend.bind((bind, 0))
        frontend.bind((bind, 0))
        return {'host': bind, 'backend_port': str(backend.getsockname()[1]),
                'frontend_port': str(frontend.getsockname()[1])}


def exercise_profile(case, source, directory, environment, profile, values, programs, host, *,
                     executable=None, offline=False, tool_label='system'):
    from contextlib import nullcontext

    password = secrets.token_urlsafe(48)
    distribution = 'packaged' if executable else 'source'
    origin = ('https://' if profile == 'prod' else 'http://') + values['host'] + ':' + values['backend_port']
    frontend = origin if profile == 'prod' else 'http://' + values['host'] + ':' + values['frontend_port']
    certificate = values.get('tls_cert_file')
    previous_job = []

    def live(url):
        case.assertEqual(url, frontend + '/app/')
        session = LiveAcceptance(origin, certificate, frontend)
        job = session.exercise(password)
        if previous_job:
            job_id, digest = previous_job[0]
            with session.request('/api/jobs/' + job_id + '/download/') as response:
                case.assertEqual(hashlib.sha256(response.read()).hexdigest(), digest)
        previous_job.append(job)

    for attempt in range(2):
        # Cover the actual EXE, selected Python, Node and future .venv before any
        # offline install, and deny network even for a previously online restart.
        network = deny_external_network(host, programs) if offline or attempt else nullcontext()
        with network:
            result = drive_form(case, source, environment, profile, cold=attempt == 0, password=password,
                                values=values, executable=executable, when_ready=live)
        record_sample(result, distribution, profile, tool_label, attempt)
        if attempt:
            case.assertEqual(result['actions'], ['run', 'stop'])
        for port in (values['backend_port'], values['frontend_port']) if profile == 'dev' else (values['backend_port'],):
            with socket.socket() as probe:
                probe.settimeout(1)
                case.assertNotEqual(probe.connect_ex((values['host'], int(port))), 0)
    case.assertEqual(len(previous_job), 2)


@unittest.skipUnless(os.name == 'nt' and os.environ.get('AWCENTER_ACCEPTANCE_SOURCE_CHECKOUT'),
                     'Requires an explicitly disposable Windows checkout and firewall control')
class NativeSourceAcceptance(unittest.TestCase):
    environment = fixtures.NativeWindowsPackageTests.environment

    def test_source_check_install_and_two_starts(self):
        from scripts.manager.operations import _project_from_layout
        from scripts.manager.payload import prepare_source_payload

        checkout = Path(os.environ['AWCENTER_ACCEPTANCE_SOURCE_CHECKOUT']).resolve()
        self.assertEqual(checkout, Path(__file__).resolve().parents[1])
        python = Path(sys.executable).resolve()
        node = Path(shutil.which('node')).resolve()
        host = socket.gethostbyname(socket.gethostname())
        with tempfile.TemporaryDirectory(prefix='awc-src-') as temporary:
            directory = Path(temporary).resolve()
            source = directory / 'source'
            prepare_source_payload(_project_from_layout(checkout), source)
            environment = self.environment(directory, network=True)
            environment['PATH'] = os.pathsep.join((str(python.parent), str(node.parent), environment['PATH']))
            values = {**connection_inputs('dev', host), 'source_mode': 'online', 'python_command': str(python)}
            programs = acceptance_programs(None, directory, source, python, node)
            exercise_profile(self, source, directory, environment, 'dev', values, programs, host)


@unittest.skipUnless(os.name == 'nt' and os.environ.get('AWCENTER_RUN_MANAGER_WINDOWS_SMOKE') == '1',
                     'Requires the packaged native Windows acceptance job')
class NativeOfflineAcceptance(unittest.TestCase):
    environment = fixtures.NativeWindowsPackageTests.environment
    copy_clean_source = fixtures.NativeWindowsPackageTests.copy_clean_source

    def test_packaged_check_install_and_two_starts_with_external_network_denied(self):
        from scripts.launcher.installation_sources import SourceSettings
        from scripts.manager.distribution import verify_distribution
        from scripts.manager.profile_resources import _install_tool

        original = Path(os.environ['AWCENTER_MANAGER_EXE']).resolve()
        self.assertTrue(verify_distribution(original.parent)['complete'])
        python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
        node = Path(shutil.which('node')).resolve()
        host = socket.gethostbyname(socket.gethostname())
        self.assertFalse(host.startswith('127.'))
        profiles, tools = acceptance_matrix(os.environ)
        for profile in profiles:
            for system in tools:
                with self.subTest(profile=profile, system=system), tempfile.TemporaryDirectory(prefix='awc-pkg-') as temp:
                    directory = Path(temp).resolve()
                    source = self.copy_clean_source(original, directory)
                    executable = source / original.name
                    shutil.copy2(original, executable)
                    shutil.copytree(original.parent / '_internal', source / '_internal')
                    shutil.copytree(original.parent / 'runtimes', source / 'runtimes')
                    environment = self.environment(directory, network=True)
                    programs = [executable, *acceptance_programs(None, directory, source, python, node)]
                    package = original.parent / 'dependencies'
                    values = {**connection_inputs(profile, host), 'source_mode': 'offline',
                              'wheels_dir': str(package / 'wheels'), 'npm_cache_dir': str(package / 'npm-cache')}
                    if system:
                        environment['PATH'] = os.pathsep.join((str(python.parent), str(node.parent), environment['PATH']))
                        values['python_command'] = str(python)
                    else:
                        # The form supports choosing a specific installed interpreter.
                        # Install that fixture from the verified bundled runtime while offline.
                        settings = SourceSettings(mode='offline', runtime_dirs=(source,))
                        with deny_external_network(host, programs), patch.dict(os.environ, environment, clear=True):
                            values['python_command'] = str(_install_tool('python', settings))
                    if profile == 'prod':
                        values.update(tls_cert_file=str(directory / 'tls/server.crt'),
                                      tls_key_file=str(directory / 'tls/server.key'))
                    exercise_profile(self, source, directory, environment, profile, values, programs,
                                     host, executable=executable, offline=True,
                                     tool_label='system' if system else 'managed')
