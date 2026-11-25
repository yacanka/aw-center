"""Contract tests for the portable Dashboard reader against a migrated AW Center database."""

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase as UnitTestCase, skipUnless
from unittest.mock import patch

from django.db import connection
from django.test import TestCase

from orgs.models import Panel, Project

from .dashboard import build_dashboard
from .models import ComplianceDocument, CoverPage, DocumentStatus, WorkflowEvent
from .offline_reader import DashboardReader, DashboardReadError, ProjectNotFound


class SourceSelectionTests(UnitTestCase):
    def test_missing_invalid_and_unrelated_files_have_safe_errors(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "selected.sqlite3"
            reader = DashboardReader(path)
            with self.assertRaises(DashboardReadError):
                reader.projects()
            self.assertFalse(path.exists())
            path.write_bytes(b"not an SQLite file")
            with self.assertRaises(DashboardReadError) as invalid:
                reader.projects()
            self.assertNotIn(str(path), str(invalid.exception))
            path.unlink()
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE other(id integer)")
            with self.assertRaises(DashboardReadError):
                reader.projects()


@skipUnless(connection.vendor == "sqlite", "The desktop source format is a migrated SQLite database.")
class OfflineParityTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.other = Project.objects.get(slug="aesa")
        self.cover = CoverPage.objects.create(project=self.project, number="CP-TEST", issue="2")
        panel = Panel.objects.create(project=self.project, name="Systems", ata="27")
        other_panel = Panel.objects.create(project=self.project, name="Systems", ata="28")
        self.today = date(2026, 7, 22)
        self.now = datetime(2026, 7, 21, 22, tzinfo=timezone.utc)
        day = timedelta(days=1)
        DocumentStatus.objects.create(project=self.project, value="review", label="Custom review")
        self.doc = ComplianceDocument.objects.create(
            project=self.project, name="Reference", cover_page=self.cover, number="D-1", issue="3",
            panel=panel, status="review", cat="  A\u00a0", moc="2", release_date=self.today - day,
            target_date=self.today - 80 * day, next_action_due_date=self.today - day,
            notes="Private notes", path="private/path",
        )
        WorkflowEvent.objects.bulk_create([
            WorkflowEvent(document=self.doc, sequence=seq, status=status, effective_date=self.today - age * day)
            for seq, status, age in [(2, "authority_review", 3), (1, "to_be_issued", 10)]
        ])
        self.late = ComplianceDocument.objects.create(
            project=self.project, name="Replanned", cover_page=self.cover, panel=other_panel,
            target_date=self.today + day, revised_target_date=self.today - day,
        )
        self.unassigned = ComplianceDocument.objects.create(
            project=self.project, name="Unassigned document", cover_page=self.cover, target_date=self.today,
        )
        ComplianceDocument.objects.create(
            project=self.project, name="Archived", cover_page=self.cover, is_archived=True,
        )
        other_cover = CoverPage.objects.create(project=self.other, number="CP-OTHER")
        ComplianceDocument.objects.create(project=self.other, name="Other", cover_page=other_cover)
        Project.objects.filter(slug="iha").update(enabled=False)
        Project.objects.create(slug="unknown-local-project", name="Out of catalog")

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "başvuru #1.sqlite3"
        # Serialize this TestCase's uncommitted fixtures, preserving the real migrated schema.
        self.path.write_bytes(connection.connection.serialize())
        self.reader = DashboardReader(self.path)

    def test_all_dashboard_scopes_dates_and_document_drilldowns_match_the_web(self):
        before = self.path.read_bytes()
        with patch("compliance.offline_reader.datetime", wraps=datetime) as clock:
            clock.now.side_effect = lambda tz: self.now.astimezone(tz)
            with patch("compliance.dashboard.timezone.now", return_value=self.now):
                expected = build_dashboard(self.project, today=self.today)
            self.assertEqual(self.reader.dashboard(self.project.slug), expected)
            docs = self.reader.documents(self.project.slug)
        self.assertEqual(len(docs), expected["total"])
        rows = {item["id"]: item for item in docs}
        self.assertEqual(rows[str(self.doc.pk)], {
            "id": str(self.doc.pk), "name": "Reference", "number": "D-1", "issue": "3",
            "status": "review", "panel": "Systems", "panel_id": str(self.doc.panel_id), "ata": "27",
            "cover_page_no": "CP-TEST", "cover_page_issue": "2", "cat": "  A\u00a0", "trimmed_cat": "A",
            "moc": "2", "delivery_bucket": "issued:review", "target_date": "2026-05-03",
            "revised_target_date": None, "release_date": "2026-07-21", "next_action_due_date": "2026-07-21",
        })
        self.assertEqual(rows[str(self.late.pk)]["delivery_bucket"], "delayed")
        self.assertEqual(rows[str(self.unassigned.pk)]["panel_id"], "unassigned")
        self.assertEqual(rows[str(self.unassigned.pk)]["delivery_bucket"], "expected")
        self.assertEqual(self.path.read_bytes(), before)

    def test_project_list_and_direct_lookups_use_same_enabled_capability_scope(self):
        projects = self.reader.projects()
        self.assertIn({"name": self.project.name, "slug": self.project.slug}, projects)
        for slug in ("iha", "hurkus", "unknown-local-project", self.project.slug + "'"):
            self.assertNotIn(slug, [project["slug"] for project in projects])
            for operation in (self.reader.dashboard, self.reader.documents):
                with self.subTest(slug=slug, operation=operation), self.assertRaises(ProjectNotFound):
                    operation(slug)

    def test_real_changes_visible_at_next_read_and_source_is_query_only(self):
        with self.reader._snapshot() as db:
            self.assertEqual(db.execute("PRAGMA trusted_schema").fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE orgs_project SET enabled = 0")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE orgs_project SET enabled = 0 WHERE slug = ?", (self.project.slug,))
        self.assertNotIn(self.project.slug, [row["slug"] for row in self.reader.projects()])

    def test_live_reads_see_committed_wal_changes_but_not_uncommitted_changes(self):
        with closing(sqlite3.connect(self.path)) as writer:
            self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            writer.execute("UPDATE orgs_project SET name = 'First' WHERE slug = ?", (self.project.slug,))
            writer.commit()
            writer.execute("UPDATE orgs_project SET name = 'Second' WHERE slug = ?", (self.project.slug,))
            self.assertIn({"slug": self.project.slug, "name": "First"}, self.reader.projects())
            writer.commit()
            self.assertIn({"slug": self.project.slug, "name": "Second"}, self.reader.projects())

    def test_finalized_backup_is_checked_before_use_and_needs_no_sidecars(self):
        with closing(sqlite3.connect(self.path)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
        reader = DashboardReader(self.path, immutable=True)
        self.assertIn({"slug": self.project.slug, "name": self.project.name}, reader.projects())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        with closing(sqlite3.connect(self.path)) as db:
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            root_page = db.execute(
                "SELECT rootpage FROM sqlite_schema WHERE name='compliance_workflowevent'"
            ).fetchone()[0]
        # Damage a register page in this disposable backup while retaining a valid schema/header.
        with self.path.open("r+b") as backup:
            backup.seek((root_page - 1) * page_size)
            backup.write(b"\x00")
        with self.assertRaises(DashboardReadError):
            reader.projects()

    def test_source_rejects_view_in_place_of_a_register_table_before_selection(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("ALTER TABLE compliance_workflowevent RENAME TO incompatible")
            db.execute("CREATE VIEW compliance_workflowevent AS SELECT * FROM incompatible")
        with self.assertRaises(DashboardReadError):
            self.reader.projects()
