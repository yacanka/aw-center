"""Read Certification Dashboard data from a locally selected AW Center SQLite file."""

from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from itertools import chain, groupby
from operator import itemgetter
from pathlib import Path
import sqlite3
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from projects.registry import get_project_definitions_by_capability

from .dashboard_analytics import UNASSIGNED_PANEL_NAME, aggregate_dashboard, publication_status


class DashboardReadError(ValueError):
    """The selected file is inaccessible, incompatible or contains invalid dashboard data."""


class ProjectNotFound(LookupError):
    """The requested project is unavailable for Certification Dashboard."""


_REQUIRED_COLUMNS = {
    "orgs_project": {"id", "slug", "name", "enabled"},
    "orgs_panel": {"id", "project_id", "name", "ata"},
    "compliance_coverpage": {"id", "project_id", "number", "issue"},
    "compliance_compliancedocument": {
        "id", "project_id", "panel_id", "cover_page_id", "name", "number", "issue", "status",
        "cat", "moc", "target_date", "revised_target_date", "release_date", "next_action_due_date",
        "is_archived", "created_at",
    },
    "compliance_workflowevent": {"document_id", "sequence", "status", "effective_date"},
    "compliance_documentstatus": {"project_id", "value", "label"},
}
_DOCUMENT_FIELDS = """
    d.id, d.name, d.number, d.issue, d.status, d.cat, d.moc,
    panel.id AS panel_id, panel.name AS panel, panel.ata,
    cover.number AS cover_page_no, cover.issue AS cover_page_issue,
    d.target_date, d.revised_target_date, d.release_date, d.next_action_due_date
"""
_DOCUMENT_TABLES = """
    FROM compliance_compliancedocument AS d
    JOIN compliance_coverpage AS cover ON cover.id = d.cover_page_id AND cover.project_id = d.project_id
    LEFT JOIN orgs_panel AS panel ON panel.id = d.panel_id AND panel.project_id = d.project_id
"""
_ACTIVE_DOCUMENTS = "WHERE d.project_id = ? AND d.is_archived = 0 ORDER BY d.created_at DESC, d.name, d.id"
_DATE_FIELDS = ("target_date", "revised_target_date", "release_date", "next_action_due_date")
_COMPLIANCE_PROJECTS = frozenset(item.slug for item in get_project_definitions_by_capability("compliance"))
try:
    _ISTANBUL = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    # Windows may lack IANA data. Only today's Istanbul date uses this timezone.
    _ISTANBUL = timezone(timedelta(hours=3))


def _validate_schema(db):
    # Require ordinary tables and stored columns. A similarly named view or virtual table
    # must never redirect dashboard reads into unrelated database content.
    for table, required in _REQUIRED_COLUMNS.items():
        table_info = db.execute(f"PRAGMA main.table_list('{table}')").fetchone()
        if table_info is None or table_info["type"] != "table":
            raise DashboardReadError("The selected file does not have a supported AW Center schema.")
        columns = db.execute(f"PRAGMA main.table_xinfo('{table}')")
        stored = {column["name"] for column in columns if column["hidden"] == 0}
        if not required.issubset(stored):
            raise DashboardReadError("The selected file does not have a supported AW Center schema.")


def _project_id(db, slug):
    if slug in _COMPLIANCE_PROJECTS:
        row = db.execute("SELECT id FROM orgs_project WHERE enabled = 1 AND slug = ?", (slug,)).fetchone()
        if row is not None:
            return row["id"]
    raise ProjectNotFound("This Certification Dashboard project is unavailable.")


def _read_document(row):
    result = dict(row)
    result["id"] = str(UUID(result["id"]))
    for field in _DATE_FIELDS:
        if result[field] is not None:
            result[field] = date.fromisoformat(result[field])
    return result


def _analytics_records(db, project_id):
    rows = db.execute(
        f"""SELECT {_DOCUMENT_FIELDS}, event.status AS event_status, event.effective_date AS event_date
            {_DOCUMENT_TABLES}
            LEFT JOIN compliance_workflowevent AS event ON event.document_id = d.id
            {_ACTIVE_DOCUMENTS}, event.sequence""",
        (project_id,),
    )
    for _, group in groupby(rows, key=itemgetter("id")):
        first = next(group)
        document = _read_document(first)
        entries = [
            (row["event_status"], date.fromisoformat(row["event_date"]))
            for row in chain((first,), group) if row["event_date"] is not None
        ]
        yield document, entries


def _public_document(row, today):
    document = _read_document(row)
    bucket = publication_status(document, today)
    document["delivery_bucket"] = f"issued:{bucket}" if document["release_date"] else bucket
    document["trimmed_cat"] = (document["cat"] or "").strip()
    if document["panel_id"] is None:
        document["panel_id"] = "unassigned"
        document["panel"] = UNASSIGNED_PANEL_NAME
    else:
        document["panel_id"] = str(document["panel_id"])
    document["ata"] = document["ata"] or ""
    for field in _DATE_FIELDS:
        if document[field] is not None:
            document[field] = document[field].isoformat()
    return document


class DashboardReader:
    """Read a local live database or an immutable, privately owned backup copy.

    Live WAL databases use SQLite's shared-memory coordination to see committed
    frames. Immutable mode is exclusively for a finalized standalone snapshot.
    """

    def __init__(self, path: Path, *, immutable=False):
        self.path = Path(path)
        self.immutable = immutable

    @contextmanager
    def _snapshot(self):
        try:
            path = self.path.resolve(strict=True)
            if not path.is_file():
                raise DashboardReadError("Select an AW Center SQLite file.")
            uri = f"{path.as_uri()}?mode=ro" + ("&immutable=1" if self.immutable else "")
            with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA trusted_schema = OFF")
                db.execute("PRAGMA query_only = ON")
                db.execute("BEGIN")
                _validate_schema(db)
                yield db
        except DashboardReadError:
            raise
        except (sqlite3.Error, OSError, ValueError, TypeError, AttributeError, OverflowError) as exc:
            raise DashboardReadError("The selected AW Center database could not be read.") from exc

    def projects(self):
        """Validate the source and return enabled projects with the installed compliance capability."""
        with self._snapshot() as db:
            if self.immutable:
                # Verify the copied register pages before replacing the last good backup.
                # Scope checks to the six dashboard tables, including empty registers.
                for table in _REQUIRED_COLUMNS:
                    result = db.execute(f"PRAGMA main.quick_check('{table}')").fetchone()
                    if result is None or result[0] != "ok":
                        raise DashboardReadError("The selected AW Center backup is damaged.")
            rows = db.execute("SELECT slug, name FROM orgs_project WHERE enabled = 1 ORDER BY name, id")
            return [dict(row) for row in rows if row["slug"] in _COMPLIANCE_PROJECTS]

    def dashboard(self, slug):
        """Return the same analytics contract as the project-scoped web dashboard."""
        with self._snapshot() as db:
            project_id = _project_id(db, slug)
            now = datetime.now(timezone.utc)
            statuses = db.execute(
                "SELECT value, label FROM compliance_documentstatus WHERE project_id = ? ORDER BY label, value",
                (project_id,),
            )
            archived = db.execute(
                "SELECT count(*) FROM compliance_compliancedocument WHERE project_id = ? AND is_archived = 1",
                (project_id,),
            ).fetchone()[0]
            return aggregate_dashboard(
                slug, _analytics_records(db, project_id), [dict(row) for row in statuses],
                archived, now.astimezone(_ISTANBUL).date(), now,
            )

    def documents(self, slug):
        """Return safe, active document fields and canonical delivery/CAT slices for drill-down."""
        with self._snapshot() as db:
            project_id = _project_id(db, slug)
            today = datetime.now(_ISTANBUL).date()
            rows = db.execute(f"SELECT {_DOCUMENT_FIELDS} {_DOCUMENT_TABLES} {_ACTIVE_DOCUMENTS}", (project_id,))
            return [_public_document(row, today) for row in rows]
