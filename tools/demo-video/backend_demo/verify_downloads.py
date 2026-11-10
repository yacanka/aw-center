"""Decode each recorded browser download and check recognisable business content."""
import hashlib
import hmac
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
from zipfile import ZipFile

from docx import Document
from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT/'artifacts/aw-center-video/.work'
DEMO_STATE = ROOT/'.runtime/aw-center-video/backend'


def package_contents(content):
    """Compare all OOXML parts while ignoring archive timestamps and compression."""
    with ZipFile(BytesIO(content)) as archive:
        members = [entry for entry in archive.infolist() if not entry.is_dir()]
        fingerprints = {entry.filename: hashlib.sha256(archive.read(entry)).digest() for entry in members}
        if len(members) != len(fingerprints):
            raise ValueError('Duplicate document package member')
        return fingerprints


def private_value_detector():
    """Return a predicate without exposing any credential or matched text."""
    known = set()
    invite_digests = set()
    for access in DEMO_STATE.rglob('access.json'):
        password = json.loads(access.read_text())['password']
        known.add(password)
        known.add(hmac.new(password.encode(), b'aw-center-video/member-password', hashlib.sha256).hexdigest() + 'aA')
    for keys in DEMO_STATE.glob('state-*/keys.json'):
        record = json.loads(keys.read_text())
        known.update(record[key] for key in ('secret', 'jira'))
    for database in DEMO_STATE.glob('state-*/demo.sqlite3'):
        connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            tables = {name for name, in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'users_userinvitation' in tables:
                invite_digests.update(value for value, in connection.execute('SELECT token_digest FROM users_userinvitation'))
            if 'django_session' in tables:
                known.update(value for value, in connection.execute('SELECT session_key FROM django_session'))
        finally:
            connection.close()
    known.discard('')
    credential = re.compile(
        r"/app/invite[#?][^\s\"<>]+|/app/login[#?](?:uid|token)=|\b[a-z0-9]{5,8}-[a-f0-9]{32}\b|"
        r"\b(?:JSESSIONID|sessionid|csrftoken|authorization|access_token|refresh_token|download_token|api_token)"
        r"\s*[:=]\s*[\"']?(?:bearer\s+)?[A-Za-z0-9_./+=-]{12,}", re.I)
    opaque = re.compile(r'(?<![\w-])[A-Za-z0-9_-]{43}(?![\w-])')
    def matches(content):
        if credential.search(content) or any(value in content for value in known):
            return True
        return any(hashlib.sha256(match.group().encode()).hexdigest() in invite_digests for match in opaque.finditer(content))

    return matches


def private_output_check():
    """Check published text and recording diagnostics against this demo's credentials."""
    matches = private_value_detector()
    published = WORK.parent
    candidates = set(published.glob('*'))
    candidates.update(WORK.glob('*'))
    candidates.update(WORK.glob('pilot/*'))
    candidates.update(WORK.glob('visual-qa/*.json'))
    candidates.update(WORK.glob('takes/*/*'))
    candidates.update(path for path in WORK.rglob('*.log') if path.relative_to(WORK).parts[0] not in {'audio', 'dist'})
    checked = 0
    for path in sorted(candidates):
        if path.suffix.lower() not in {'.md','.csv','.srt','.ass','.json','.jsonl','.txt','.log','.vtt','.yaml','.yml'} or not path.is_file():
            continue
        content = path.read_text(encoding='utf-8', errors='replace')
        if matches(content):
            raise ValueError('Private value in recording output: ' + str(path.relative_to(published)))
        checked += 1
    return checked


def decode(name, content):
    ext = Path(name).suffix.lower()
    stream = BytesIO(content)
    if ext=='.docx':
        doc = Document(stream)
        assert any(p.text.strip() for p in doc.paragraphs) or doc.tables, name
        return {'format':'DOCX','paragraphs':len(doc.paragraphs),'tables':len(doc.tables)}
    if ext=='.xlsx':
        book=load_workbook(stream,read_only=True,data_only=True)
        try:
            assert any(any(any(cell is not None for cell in row) for row in sheet.values) for sheet in book.worksheets),name
            return {'format':'XLSX','sheets':book.sheetnames}
        finally:
            book.close()
    if ext=='.pdf':
        doc=PdfReader(stream,strict=True)
        assert len(doc.pages)>0
        return {'format':'PDF','pages':len(doc.pages)}
    if ext=='.zip':
        with ZipFile(stream) as archive:
            assert archive.namelist() and archive.testzip() is None
            members = {}
            for item in archive.infolist():
                assert not Path(item.filename).is_absolute() and '..' not in Path(item.filename).parts,item.filename
                if not item.is_dir():
                    members[item.filename]=decode(item.filename,archive.read(item))
            return {'format':'ZIP','members':members}
    if ext in {'.jpg','.jpeg','.png','.webp'}:
        with Image.open(stream) as img:
            img.load()
            return {'format':img.format,'width':img.width,'height':img.height}
    if ext=='.json':
        parsed=json.loads(content)
        assert isinstance(parsed,(dict,list)) and parsed
        return {'format':'JSON','top_level':list(parsed) if isinstance(parsed,dict) else len(parsed)}
    raise ValueError(f'Unverified download format {ext}')


def validate():
    root=WORK/'downloads'
    output={}
    for file in sorted(root.glob('*/*')):
        if not (file.is_file() and not file.name.startswith('.')):
            continue
        data=file.read_bytes()
        key=str(file.relative_to(root))
        detail=decode(file.name,data)
        detail['bytes']=len(data)
        detail['sha256']=hashlib.sha256(data).hexdigest()
        if file.parent.name=='outlook':
            original = (DEMO_STATE/'examples/atlas.docx').read_bytes()
            assert package_contents(data) == package_contents(original), 'Outlook document contents differ'
        if file.parent.name=='pilot':
            assert Document(BytesIO(data)).paragraphs[0].text=='Atlas document management plan'
        if file.parent.name=='baglama':
            receipt=json.loads(data)
            assert receipt['mode']=='link' and receipt['summary']['matched_targets']==4
        if file.parent.name=='document-analysis':
            report=json.loads(data)
            assert report['checks'] and any(check['evidence'] for check in report['checks'])
        output[key]=detail
    assert output
    (WORK/'verified-downloads.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    checked = private_output_check()
    print(f'{len(output)} browser downloads decoded and hashed; {checked} text outputs passed credential checks.')


if __name__=='__main__':
    validate()
