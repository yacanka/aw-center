"""Acceptance checks for the database source and browser session of the local viewer."""

from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import patch
import unittest
from urllib.parse import urlencode

from scripts.certification_viewer.source import DatabaseSource, SourceError
from scripts.certification_viewer.server import ViewerServer


class SampleReader:
    """Exercise real file and transaction handling with a small, synthetic schema."""

    def __init__(self, path, *, immutable=False):
        self.path = path

    def projects(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        try:
            return [{'slug': 'test', 'name': db.execute('SELECT name FROM project').fetchone()[0]}]
        finally:
            db.close()

    def documents(self, slug):
        return self.projects()


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / 'örnek proje.db'
        db = sqlite3.connect(self.file)
        db.execute('CREATE TABLE project(name TEXT)')
        db.execute("INSERT INTO project VALUES ('Bir')")
        db.commit()
        db.close()
        self.source = DatabaseSource(self.root, SampleReader, network_path=lambda _: True)

    def test_failed_refresh_retains_validated_snapshot_and_read_time(self):
        initial = self.source.select(self.file)
        self.assertEqual(initial['source_kind'], 'backup')
        self.file.write_bytes(b'incomplete backup')
        with self.assertRaises(SourceError):
            self.source.refresh()
        current = self.source.status()
        self.assertEqual(current['projects'], initial['projects'])
        self.assertEqual(current['read_at'], initial['read_at'])
        self.assertTrue(current['warning'])
        self.assertEqual(self.source.read('documents', 'test'), initial['projects'])

    def test_concurrent_refresh_keeps_original_untouched(self):
        original = self.file.read_bytes()
        self.source.select(self.file)
        with ThreadPoolExecutor(max_workers=2) as executor:
            states = list(executor.map(lambda _: self.source.refresh(), range(2)))
        self.assertEqual(states[0]['projects'], states[1]['projects'])
        self.assertEqual(self.file.read_bytes(), original)

    def test_available_snapshot_remains_readable_during_replacement(self):
        self.source.select(self.file)
        started, release = Event(), Event()

        def stalled_backup(*args):
            started.set()
            release.wait(2)
            raise SourceError('Simulated interruption')

        with patch('scripts.certification_viewer.source._copy_backup', stalled_backup), ThreadPoolExecutor(2) as pool:
            refresh = pool.submit(self.source.refresh)
            self.assertTrue(started.wait(1))
            try:
                read = pool.submit(self.source.read, 'documents', 'test')
                self.assertEqual(read.result(timeout=1)[0]['name'], 'Bir')
            finally:
                release.set()
            with self.assertRaises(SourceError):
                refresh.result()
        self.source.close()
        self.assertEqual(list(self.root.glob('*.db')), [self.file])
        with self.assertRaises(SourceError):
            self.source.refresh()

    def test_network_journal_rejected(self):
        Path(str(self.file) + '-wal').write_bytes(b'pending')
        with self.assertRaises(SourceError):
            self.source.select(self.file)

    def test_browser_handoff_is_single_use_and_private(self):
        self.source.select(self.file)
        (self.root / 'index.html').write_text('<meta name="dashboard-session" content="__DASHBOARD_SESSION__">')
        server = ViewerServer(self.source, self.root)
        self.addCleanup(server.server_close)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)

        def request(method, path, body=None, headers=None):
            conn = HTTPConnection(*server.server_address, timeout=3)
            try:
                conn.request(method, path, body, headers or {})
                response = conn.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                conn.close()

        self.assertEqual(request('GET', '/viewer/projects')[0], 403)
        token = server.new_ticket()
        body = urlencode({'ticket': token})
        status, headers, _ = request('POST', '/open', body)
        self.assertEqual(status, 303)
        self.assertEqual(request('POST', '/open', body)[0], 403)
        self.assertEqual(request('GET', headers['Location'])[0], 403)
        status, _, page = request('GET', headers['Location'], headers={'Cookie': headers['Set-Cookie'].split(';')[0]})
        self.assertEqual(status, 200)
        self.assertIn(server.session.encode(), page)
        auth = {'X-Dashboard-Session': server.session}
        self.assertEqual(json.loads(request('GET', '/viewer/projects', headers=auth)[2])['projects'][0]['slug'], 'test')
        self.assertEqual(request('GET', '/viewer/projects', headers={**auth, 'Host': 'other.example'})[0], 403)
        self.assertEqual(request('POST', '/viewer/refresh', headers={**auth, 'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(request('GET', '/assets/../index.html', headers=auth)[0], 404)


@unittest.skipUnless(os.name == 'nt', 'Uses native Windows path selection and Tk.')
class WindowsFileSelectionTests(unittest.TestCase):
    def test_missing_embedded_path_can_be_replaced_and_remembered(self):
        import tkinter as tk
        from time import monotonic, sleep

        from scripts.verify_certification_exe import seed
        from scripts.certification_viewer.desktop import ViewerWindow, remembered_source

        with TemporaryDirectory() as work, patch.dict(os.environ, LOCALAPPDATA=work):
            directory = Path(work)
            embedded = str(directory / 'missing.sqlite3')
            alternate = directory / 'Türkçe dosya.db'
            seed(alternate, 1)
            root = tk.Tk()
            root.withdraw()

            def wait_for(predicate):
                deadline = monotonic() + 10
                while not predicate() and monotonic() < deadline:
                    root.update()
                    sleep(.02)
                self.assertTrue(predicate())

            with patch('scripts.certification_viewer.desktop.browser_handoff', return_value=True) as handoff:
                app = ViewerWindow(root, directory, directory, embedded, False)
                try:
                    wait_for(lambda: 'bulunamadı' in app.status.get())
                    handoff.assert_not_called()
                    app.path.set(str(alternate))
                    app.open()
                    wait_for(lambda: handoff.called)
                    self.assertEqual(remembered_source(app.preference), str(alternate))
                    self.assertEqual(app.server.source.read('dashboard', 'ozgur')['total'], 1)
                finally:
                    app.close()
                    root.mainloop()
