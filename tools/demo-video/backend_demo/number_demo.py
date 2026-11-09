"""Stateful numbering-provider double for the isolated video generation only."""
from contextlib import closing
import os
from pathlib import Path
import re
import secrets
import sqlite3

FORMAT = "ATL-KAPAK"


def install():
    from django.conf import settings
    from integrations.numarator.client import NumaratorClient, NumaratorRejectedError

    if os.environ.get("AW_VIDEO_DEMO") != "1":
        raise RuntimeError("The numbering adapter requires the video profile.")
    generation = Path(os.environ["AW_DEMO_GENERATION"])
    if Path(settings.DATABASES["default"]["NAME"]).resolve() != generation / "demo.sqlite3":
        raise RuntimeError("The numbering adapter requires the isolated database.")
    database = generation / "numarator.sqlite3"
    settings.NUMARATOR_ENABLED = True
    settings.NUMARATOR_BASE_URL = "https://numarator.example.invalid"
    settings.NUMARATOR_CREDENTIAL_ID = "video-local"
    settings.NUMARATOR_PROJECT_FORMATS = {"gokbey": [FORMAT]}
    # Purely local, ephemeral transport placeholder. No upstream key exists.
    settings.NUMARATOR_API_KEY = secrets.token_urlsafe(24)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS numbers(
            id INTEGER PRIMARY KEY, external_reference TEXT UNIQUE NOT NULL,
            idempotency TEXT UNIQUE NOT NULL, status TEXT NOT NULL)""")

    def request(client, method, path, *, body=None, headers=None):
        if method == "GET" and path == f"/api/private/v1/formats/{FORMAT}/":
            return {"data": {"code": FORMAT, "required_context": [
                {"key": "seri", "required": True, "default": None, "max_length": 6}
            ]}}
        with closing(sqlite3.connect(database, timeout=5)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if method == "POST" and path == "/api/private/v1/numbers/":
                if body["format_code"] != FORMAT or body.get("context_data", {}).get("seri") != "ATL":
                    raise NumaratorRejectedError("Demo series must be ATL.")
                reference, key = body["external_reference"], headers["Idempotency-Key"]
                connection.execute(
                    "INSERT OR IGNORE INTO numbers(external_reference,idempotency,status) VALUES(?,?,'active')",
                    (reference,key))
                row = connection.execute("SELECT id,status FROM numbers WHERE external_reference=? AND idempotency=?",
                                         (reference,key)).fetchone()
            elif method == "PATCH" and (match := re.fullmatch(r"/api/private/v1/numbers/([0-9]+)/status/",path)):
                connection.execute("UPDATE numbers SET status='used' WHERE id=?", (int(match[1]),))
                row = connection.execute("SELECT id,status FROM numbers WHERE id=?", (int(match[1]),)).fetchone()
            else:
                raise NumaratorRejectedError("Unknown demo numbering operation.")
            if row is None:
                raise NumaratorRejectedError("Unknown demo numbering request.")
            return {"data": {"id": row[0], "document_number": f"ATL-KAP-{row[0]:04}",
                             "format_code": FORMAT, "status": row[1]}}

    NumaratorClient._request = request
