"""Runtime version probes must not inherit the Manager control channel."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.launcher import process, toolchain
from scripts.launcher.model import LauncherError


class RuntimeValidationTests(unittest.TestCase):
    def test_cancelled_version_check_does_not_start_a_process(self):
        stop = threading.Event()
        stop.set()
        with process.operation_control(stop):
            with self.assertRaises(process.OperationCancelled):
                toolchain._check_version(Path(sys.executable), '1.2.3')

    def run_with_control_pipe(self, body, *arguments):
        program = '''import os, sys, threading
from pathlib import Path
from unittest.mock import patch
from scripts.launcher import process, toolchain
reading = threading.Event()
def controls():
    reading.set()
    os.read(sys.stdin.fileno(), 1)
threading.Thread(target=controls, daemon=True).start()
assert reading.wait(2)
original_run = toolchain.subprocess.run
def bounded_run(command, **options):
    options['timeout'] = 0.5
    return original_run(command, **options)
'''
        child = subprocess.Popen([sys.executable, '-c', program + body, *map(str, arguments)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            child.wait(timeout=15)
            output, errors = child.stdout.read(), child.stderr.read()
            self.assertEqual(child.returncode, 0, errors.decode('utf-8', errors='replace'))
            return output.splitlines()
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

    def test_version_check_finishes_with_the_manager_pipe_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary).resolve() / 'version.py'
            script.write_text('import sys; assert sys.stdin.read() == ""; print("1.2.3")', encoding='utf-8')
            output = self.run_with_control_pipe('''
with process.operation_control(threading.Event()), patch.object(toolchain.subprocess, 'run', side_effect=bounded_run):
    toolchain._check_version(Path(sys.argv[1]), '1.2.3', node=Path(sys.executable))
print('validated')
''', script)
        self.assertEqual(output, [b'validated'])

    def test_cancellation_stops_a_running_version_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary).resolve() / 'version.py'
            script.write_text('import time; time.sleep(30); print("1.2.3")', encoding='utf-8')
            stop = threading.Event()
            timer = threading.Timer(0.2, stop.set)
            original = subprocess.run
            def bounded_run(command, **options):
                options['timeout'] = 0.5
                return original(command, **options)
            timer.start()
            try:
                with process.operation_control(stop), patch.object(toolchain.subprocess, 'run', side_effect=bounded_run):
                    with self.assertRaises(process.OperationCancelled):
                        toolchain._check_version(script, '1.2.3', node=Path(sys.executable))
            finally:
                timer.cancel()

    def test_probe_errors_keep_safe_codes_and_numeric_details(self):
        denied = PermissionError(13, 'private-path-detail')
        denied.winerror = 5
        cases = (
            (denied, 'runtime_validation_start_failed', '5'),
            (subprocess.TimeoutExpired('private-command', 30), 'runtime_validation_timeout', None),
            (subprocess.CompletedProcess([], 17, 'private-stdout', 'private-stderr'), 'runtime_validation_process_failed', '17'),
            (subprocess.CompletedProcess([], 0, '99.0.0', 'private-stderr'), 'runtime_validation_version_mismatch', None),
        )
        for outcome, code, numeric in cases:
            with self.subTest(code=code):
                options = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
                with patch.object(toolchain.subprocess, 'run', **options):
                    with self.assertRaises(LauncherError) as caught:
                        toolchain._check_version(Path('npm-cli.js'), '10.9.4', node=Path(sys.executable))
                self.assertEqual(getattr(caught.exception, 'code', None), code)
                self.assertIn('npm', str(caught.exception))
                self.assertNotIn('private-', str(caught.exception))
                if numeric:
                    self.assertIn(numeric, str(caught.exception))

    def test_manager_reports_runtime_probe_failure_instead_of_operation_failed(self):
        from scripts.manager import operations
        events = []
        def fail(action, args, emit):
            args.progress('npm runtime sürümü doğrulanıyor')
            raise toolchain.RuntimeValidationError('process_failed', 'npm', returncode=17)
        with patch.object(operations, '_dispatch', side_effect=fail):
            operations.execute({'action': 'bundle'}, events.append, lambda: None, threading.Event())
        error = next(event for event in events if event['type'] == 'error')
        self.assertEqual(error['code'], 'runtime_validation_process_failed')
        self.assertIn('npm', error['message'])
        self.assertIn('17', error['message'])
        self.assertTrue(error['remedy'])

    @unittest.skipUnless(os.environ.get('AWCENTER_RUN_RUNTIME_PROBE_SMOKE') == '1',
                         'Real npm archive acceptance requires explicit network/local archive opt-in')
    def test_real_npm_install_and_version_with_pending_control_read(self):
        from scripts.launcher.installation_sources import SourceSettings, fetch_artifact, load_catalog, _verify
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Acceptance requires an installed Node executable')
        artifact = load_catalog()['npm']
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            if selected := os.environ.get('AWCENTER_NPM_TEST_ARCHIVE'):
                archive = Path(selected)
                _verify(archive, artifact)
            else:
                archive = fetch_artifact(artifact, home / 'cache', SourceSettings())
            (home / 'runtimes').mkdir()
            output = self.run_with_control_pipe('''
from scripts.launcher.installation_sources import load_catalog
with process.operation_control(threading.Event()):
    toolchain._install(Path(sys.argv[1]), load_catalog()['npm'], Path(sys.argv[2]), node=Path(sys.argv[3]))
print('npm installed and validated')
''', home, archive, Path(node).resolve())
            self.assertEqual(output, [b'npm installed and validated'])
            self.assertTrue((home / 'runtimes/npm-10.9.4/.awcenter-tool.json').is_file())

    @unittest.skipUnless(sys.platform == 'win32' and os.environ.get('AWCENTER_RUN_RUNTIME_PROBE_SMOKE') == '1',
                         'Exact user-version acceptance requires native Windows and explicit archive opt-in')
    def test_node_26121_npm_11180_are_reused_without_runtime_downloads(self):
        from scripts.launcher.installation_sources import Artifact, SourceSettings, fetch_artifact, safe_extract
        node = Path(shutil.which('node')).resolve()
        version = subprocess.run([str(node), '--version'], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        self.assertEqual(version, 'v26.12.1', 'Acceptance must reproduce the issue reporter\'s Node version')
        artifact = Artifact('npm', '11.18.0', 'npm-11.18.0.tgz',
                            'https://registry.npmjs.org/npm/-/npm-11.18.0.tgz',
                            '73f6155215ebabf4ed96dca1f567c2372cc713c33af2e5b9b62fde4e92373e2e',
                            'tar.gz', 'package/bin/npm-cli.js')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = fetch_artifact(artifact, root / 'fixtures', SourceSettings())
            safe_extract(archive, root / 'npm-source', 'tar.gz')
            prefix = root / 'operator-node'
            (prefix / 'node_modules').mkdir(parents=True)
            shutil.move(str(root / 'npm-source/package'), str(prefix / 'node_modules/npm'))
            executable = prefix / 'node.exe'
            shutil.copyfile(node, executable)
            python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
            output = self.run_with_control_pipe('''
from scripts.launcher.installation_sources import SourceSettings
with process.operation_control(threading.Event()), patch.object(toolchain, 'fetch_artifact', side_effect=AssertionError('Runtime download was not expected')):
    values = toolchain.ensure_toolchain(Path(sys.argv[1]), SourceSettings(), python_executable=Path(sys.argv[2]), node_executable=Path(sys.argv[3]))
    assert Path(values['AWCENTER_MANAGED_NODE']) == Path(sys.argv[3])
    assert Path(values['AWCENTER_MANAGED_NPM_CLI']) == Path(sys.argv[4])
print('system Python, Node 26.12.1 and npm 11.18.0 reused')
''', root / 'private', python, executable, prefix / 'node_modules/npm/bin/npm-cli.js')
            self.assertEqual(output, [b'system Python, Node 26.12.1 and npm 11.18.0 reused'])
