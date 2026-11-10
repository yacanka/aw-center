"""Local JIRA provider for the explicitly isolated film set.

The real JIRA session, project roles, Watcher, draft, preflight, PDF validation,
durable job state, polling, artifacts and idempotency all stay in Django.
"""
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace as Record

COMPONENT = "Atlas Demo"
PARENT_TITLES = {
    101: "Atlas belge dizini ve sürüm kontrolü",
    102: "Atlas teslim dosyalarının gözden geçirilmesi",
    103: "Atlas toplantı tutanağı ve karar listesi",
}
AS = "Deniz Örnek"


def state_path():
    from django.conf import settings

    if os.environ.get("AW_VIDEO_DEMO") != "1" or settings.JIRA_URL.rstrip("/") != "https://jira.example.invalid":
        raise RuntimeError("The video JIRA provider requires the isolated demo settings.")
    return Path(settings.DATABASES["default"]["NAME"]).with_name("jira-provider.sqlite3")


def db():
    handle = sqlite3.connect(state_path(), timeout=8)
    handle.row_factory = sqlite3.Row
    return handle


def issue_fields(summary, subtask=False, done=False):
    return {
        "summary": summary,
        "description": "Atlas örnek belge yönetimi için tanımlanan çalışma.",
        "issuetype": {"name": "Sub-task" if subtask else "Task", "subtask": subtask},
        "status": {
            "name": "Tamamlandı" if done else "İncelemede",
            "statusCategory": {"key": "done" if done else "indeterminate"},
        },
        "components": [{"name": COMPONENT}],
        "assignee": {"name": "D10001", "displayName": AS, "emailAddress": "deniz@example.invalid"},
        "updated": "2026-11-03T12:00:00+03:00",
        "customfield_45005": AS,
    }


def resource(value):
    if isinstance(value, dict):
        return Record(**{key: resource(child) for key, child in value.items()})
    if isinstance(value, list):
        return [resource(child) for child in value]
    return value


class LocalJira:
    def myself(self):
        return {"name": "D10001", "displayName": AS}

    def issue(self, key, **unused):
        from jira import JIRAError

        with closing(db()) as connection:
            row = connection.execute("SELECT * FROM issue WHERE issue_key = ?", (key,)).fetchone()
            if row is None:
                raise JIRAError(status_code=404)
            fields = json.loads(row["fields"])
            children = connection.execute(
                "SELECT issue_key, fields FROM issue WHERE parent = ? ORDER BY id", (key,)
            ).fetchall()
            fields["subtasks"] = [
                {"key": child["issue_key"], "fields": json.loads(child["fields"])} for child in children
            ]
            fields["attachment"] = [
                {"filename": item["filename"]} for item in connection.execute(
                    "SELECT filename FROM attachment WHERE issue_key=?", (key,)
                )
            ]
        return Record(key=key, fields=resource(fields), raw={"fields": fields})

    def createmeta(self, **unused):
        fields = {
            "summary": {"name": "Summary", "required": True, "schema": {"type": "string"}},
            "description": {"name": "Description", "schema": {"type": "string"}},
            "labels": {"name": "Labels", "schema": {"type": "array", "items": "string"}},
            "priority": {"name": "Priority", "schema": {"type": "priority"},
                         "allowedValues": [{"id": "3", "name": "Normal"}]},
        }
        return {"projects": [{"issuetypes": [{"fields": fields}]}]}

    def search_issues(self, query, **unused):
        match = re.fullmatch(r'labels = "([^"]+)" ORDER BY created ASC', query)
        if not match:
            raise ValueError("Unsupported local JIRA query.")
        with closing(db()) as connection:
            for row in connection.execute("SELECT issue_key, fields FROM issue ORDER BY id"):
                if match[1] in json.loads(row["fields"]).get("labels", []):
                    return [Record(key=row["issue_key"])]
        return []

    def create_issue(self, fields):
        parent = (fields.get("parent") or {}).get("key")
        payload = issue_fields(fields["summary"], bool(parent))
        for key in ("summary", "description", "labels", "priority", "duedate"):
            if key in fields:
                payload[key] = fields[key]
        with closing(db()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            key = "DEMO-" + str(connection.execute("SELECT COALESCE(MAX(id), 0)+301 FROM issue").fetchone()[0])
            connection.execute("INSERT INTO issue (issue_key, parent, fields) VALUES(?,?,?)",
                               (key, parent, json.dumps(payload, ensure_ascii=False)))
        return Record(key=key)

    def add_attachment(self, issue, attachment, filename):
        import hashlib
        digest = hashlib.sha256(attachment.read()).hexdigest()
        with closing(db()) as connection, connection:
            connection.execute("INSERT OR REPLACE INTO attachment VALUES(?,?,?)", (issue, filename, digest))
        return Record(filename=filename)


def install():
    from integrations.jira import client, watcher_assessment

    state_path()

    def initialize(connector, server_url, jira_session_id=None, *, personal_access_token=None):
        if server_url.rstrip("/") != "https://jira.example.invalid":
            raise ValueError("Unknown JIRA origin in video demo.")
        connector.jira = LocalJira()
        connector.issue_key = None

    def assess(prompt):
        snapshot = json.loads(prompt.rsplit("\nBelge verisi:\n", 1)[1])
        return (f"{snapshot['ecr_number']} · {snapshot['title']}\n"
                "Temsili değerlendirme: Belge dizinindeki güncelleme, yayın sorumlusunun "
                "incelemesine sunulmalıdır. Karar ve imza proje ekibine aittir.")

    client.JiraConnector.__init__ = initialize
    watcher_assessment.request_assessment = assess


def seed(main_user, other_user, project, examples_path):
    from automations.ecr_parser import parse_ecr_pdf
    from automations.test_ecr_workflow import pdf_document, table_commands
    from docx import Document
    from django.conf import settings
    from integrations.jira.workflow_models import JiraTrackedIssue
    from openpyxl import Workbook

    examples = Path(examples_path)
    with closing(db()) as connection, connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS issue(id INTEGER PRIMARY KEY, issue_key TEXT UNIQUE,
                parent TEXT, fields TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attachment(issue_key TEXT, filename TEXT, sha256 TEXT,
                PRIMARY KEY(issue_key, filename));
            DELETE FROM attachment;
            DELETE FROM issue;
        """)
        for number, title in PARENT_TITLES.items():
            fields = issue_fields(title)
            fields.update(customfield_45000=f"ECD-{number}", customfield_45001="B",
                          customfield_45002=f"ATL-DCC-{number}")
            connection.execute("INSERT INTO issue(issue_key,fields) VALUES(?,?)",
                               (f"DEMO-{number}", json.dumps(fields, ensure_ascii=False)))
            for offset, summary in enumerate(("Belge dizinini incele", "Sürüm geçmişini doğrula")):
                fields = issue_fields(summary, subtask=True, done=bool(offset))
                connection.execute("INSERT INTO issue(issue_key,parent,fields) VALUES(?,?,?)",
                                   (f"DEMO-{number * 10 + offset}", f"DEMO-{number}", json.dumps(fields)))
    for number in (101, 103):
        row, _ = JiraTrackedIssue.objects.update_or_create(
            owner=main_user, issue=f"DEMO-{number}",
            defaults={"title": PARENT_TITLES[number], "components": [COMPONENT]},
        )
        row.projects.set([project])
        row.assigned_users.set([other_user])
    book = Workbook()
    book.active.append(["İş başlığı", "Açıklama"])
    book.active.append(["Teslim dizinini incele", "Hazırlanan dosya listesini kontrol et."])
    book.active.append(["Revizyon özetini yaz", "Kayıt geçmişiyle karşılaştır."])
    book.save(examples / "alt-gorevler.xlsx")
    doc = Document()
    doc.add_heading("Atlas | Değişiklik inceleme formu", 0)
    doc.add_paragraph("{{ DCC_Form_Number }} · {{ Design_Change_Title }}")
    doc.add_paragraph("Belge: {{ Design_Change_Number }} / {{ Design_Change_Revision }}")
    doc.add_paragraph("Bu belge kurgusal Atlas proje verileriyle oluşturulmuştur.")
    template_dir = Path(settings.CUSTOM_TEMPLATE_DIR)
    template_dir.mkdir(parents=True, exist_ok=True)
    doc.save(template_dir / "Atlas-DCC.docx")
    policy = Path(settings.GOKBEY_DCC_POLICY_FILE)
    policy.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(policy, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
        json.dump({"schema_version": 1, "panel_responsibles": {
            "flight": "Ekin Örnek", "human factor": "Deniz Örnek",
            "electrical systems/e3": "Ada Örnek",
        }}, stream, ensure_ascii=False)
    policy.chmod(0o600)
    cells = {
        (2, 0): "Belge dizini revizyonu", (4, 0): "ECD-101", (4, 1): "Atlas Demo",
        (4, 2): "Minor", (4, 3): "Belge", (7, 0): "Rev B", (9, 1): "Atlas",
        (10, 1): "Dokumantasyon", (11, 1): "Deniz", (13, 1): "Ekin",
        (14, 1): "01/00", (15, 1): "Dizin takibi", (16, 1): "Listeyi yenile",
        (17, 1): "Eski dizin", (18, 1): "Belge ekibi",
    }
    pdf = examples / "ECD-101.pdf"
    pdf.write_bytes(pdf_document(table_commands(cells)))
    with pdf.open("rb") as handle:
        assert parse_ecr_pdf(handle)["ecr_number"] == "ECD-101"
