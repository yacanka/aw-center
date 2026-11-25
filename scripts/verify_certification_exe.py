"""Exercise an actual personalized onefile on Windows against disposable records."""

from argparse import ArgumentParser
from contextlib import closing
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from compliance.executable_config import database_path_trailer


def seed(path, count):
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE orgs_project (id INTEGER PRIMARY KEY, slug TEXT, name TEXT, enabled INTEGER);
            CREATE TABLE orgs_panel (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, ata TEXT);
            CREATE TABLE compliance_coverpage (id INTEGER PRIMARY KEY, project_id INTEGER, number TEXT, issue TEXT);
            CREATE TABLE compliance_documentstatus (project_id INTEGER, value TEXT, label TEXT);
            CREATE TABLE compliance_workflowevent (document_id TEXT, sequence INTEGER, status TEXT, effective_date TEXT);
            CREATE TABLE compliance_compliancedocument (
                id TEXT PRIMARY KEY, project_id INTEGER, panel_id INTEGER, cover_page_id INTEGER, name TEXT,
                number TEXT, issue TEXT, status TEXT, cat TEXT, moc TEXT, target_date TEXT, revised_target_date TEXT,
                release_date TEXT, next_action_due_date TEXT, is_archived INTEGER, created_at TEXT);
            INSERT INTO orgs_project VALUES (1, 'ozgur', 'Test project', 1);
            INSERT INTO orgs_panel VALUES (1, 1, 'Test panel', '27');
            INSERT INTO compliance_coverpage VALUES (1, 1, 'T-1', '1');
            INSERT INTO compliance_documentstatus VALUES (1, 'to_be_issued', 'To be issued');
        """)
        db.executemany(
            "INSERT INTO compliance_compliancedocument VALUES (?,1,1,1,?,?,'1','to_be_issued','A','1',"
            "'2025-01-01',NULL,NULL,NULL,0,'2025-01-01')",
            ((f'{i:032x}', f'Test document {i}', str(i)) for i in range(1, count + 1)),
        )
        db.commit()


class BrowserPage(HTMLParser):
    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == 'form':
            self.action = fields['action']
        if tag == 'input' and fields.get('name') == 'ticket':
            self.ticket = fields['value']
        if tag == 'meta' and fields.get('name') == 'dashboard-session':
            self.session = fields['content']
        if tag == 'script' and 'src' in fields:
            self.script = fields['src']


def publish_backup(database, destination):
    staging = destination.with_suffix('.publishing')
    with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(staging)) as copy:
        source.backup(copy)
    staging.replace(destination)


def run(directory, count, share=None):
    db = directory / 'Test kaynağı.sqlite3'
    seed(db, count)
    selected = share / 'Dashboard yedeği.db' if share else db
    if share:
        publish_backup(db, selected)
    exe = directory / 'CertificationDashboard.exe'
    shutil.copyfile(ROOT / 'packaging/dist' / exe.name, exe)
    with exe.open('ab') as stream:
        stream.write(database_path_trailer(str(selected), auto_open_network=bool(share)))
    # Intercept the default browser for automation. Production uses the same local HTML handoff.
    env = {**os.environ, 'TEMP': str(directory), 'TMP': str(directory), 'LOCALAPPDATA': str(directory),
           'BROWSER': f'"{Path(sys.executable).as_posix()}" -c pass %s'}
    start = monotonic()
    proc = subprocess.Popen([str(exe)], env=env, cwd=directory)
    try:
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        page = BrowserPage()
        while monotonic() - start < 60:
            if proc.poll() is not None:
                raise RuntimeError(f'Frozen viewer exited before browser handoff ({proc.returncode}).')
            html = next(directory.glob('AW-Certification-*/open.html'), None)
            if html and html.stat().st_size:
                page.feed(html.read_text(encoding='utf-8'))
                if hasattr(page, 'ticket'):
                    break
            sleep(0.1)
        else:
            raise TimeoutError('The packaged application did not open its dashboard.')
        origin = page.action.removesuffix('/open')
        with opener.open(page.action, urlencode({'ticket': page.ticket}).encode(), timeout=10) as reply:
            page.feed(reply.read().decode())
        with opener.open(origin + page.script, timeout=10) as script:
            assert len(script.read()) > 1000

        def query(path, method='GET'):
            request = Request(origin + '/viewer/' + path, method=method, headers={'X-Dashboard-Session': page.session})
            with opener.open(request, timeout=30) as response:
                return json.load(response)

        initial = query('projects')
        assert initial['source_kind'] == ('backup' if share else 'local')
        assert initial['projects'] == [{'slug': 'ozgur', 'name': 'Test project'}]
        assert query('projects/ozgur/dashboard')['total'] == count
        first_read = monotonic() - start
        assert len(query('projects/ozgur/documents')) == count
        with closing(sqlite3.connect(db)) as writer:
            writer.execute("UPDATE compliance_compliancedocument SET is_archived=1 WHERE id=?", (f'{1:032x}',))
            writer.commit()
        if share:
            # Simulate a broken publication. The last verified snapshot must survive.
            selected.write_bytes(b'incomplete backup')
            try:
                query('refresh', 'POST')
            except HTTPError as error:
                assert error.code == 409
            else:
                raise AssertionError('The damaged backup was accepted.')
            assert query('projects')['read_at'] == initial['read_at']
            assert query('projects/ozgur/dashboard')['total'] == count
            publish_backup(db, selected)
        refresh = monotonic()
        query('refresh', 'POST')
        latest = query('projects/ozgur/dashboard')
        assert latest['total'] == count - 1 and latest['archived'] == 1
        print(f'EXE {exe.stat().st_size:,} bytes; {count} documents; '
              f'launch to first dashboard response {first_read:.2f}s; refresh {monotonic() - refresh:.2f}s.')
    finally:
        if proc.poll() is None:
            # Only our synthetic acceptance process and its onefile child.
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=15)
            proc.wait(timeout=10)


if __name__ == '__main__':
    if os.name != 'nt':
        raise SystemExit('Run this smoke check on Windows.')
    parser = ArgumentParser()
    parser.add_argument('--share-root', type=Path, help='Existing disposable UNC share for the SMB acceptance test.')
    args = parser.parse_args()
    with TemporaryDirectory(prefix='certification-smoke-', ignore_cleanup_errors=True) as temp:
        if args.share_root:
            with TemporaryDirectory(dir=args.share_root) as share:
                run(Path(temp), 2500, Path(share))
        else:
            run(Path(temp), 2500)
