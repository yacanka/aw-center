"""Migration regression coverage for legacy CompDoc workflow evidence."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


PROJECT_TARGETS = [
    ("aesa", "0030_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ("blok30", "0017_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ("blok4050", "0006_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ("gokbey", "0006_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ("havasoj", "0020_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ("hys", "0017_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ("ozgur", "0023_compdoc_archive_reason_compdoc_archived_at_and_more"),
    ("piku", "0027_compdoc_archive_reason_compdoc_archived_at_and_more"),
]


class CompDocLifecycleMigrationTests(TransactionTestCase):
    """Verify valid events backfill without changing malformed source JSON."""

    serialized_rollback = True

    def test_backfill_compacts_sequence_and_preserves_legacy_json(self):
        executor = MigrationExecutor(connection)
        before = [("common", "0016_compdocreviewtask_compdocworkflowevent"), *PROJECT_TARGETS]
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        document = self._legacy_document(old_apps)

        executor = MigrationExecutor(connection)
        after = [("common", "0017_backfill_compdoc_workflow_events"), *PROJECT_TARGETS]
        executor.migrate(after)
        new_apps = executor.loader.project_state(after).apps
        events = new_apps.get_model("common", "CompDocWorkflowEvent").objects.order_by("sequence")
        migrated = new_apps.get_model("ozgur", "CompDoc").objects.get(pk=document.pk)

        self.assertEqual(list(events.values_list("sequence", flat=True)), [1, 2])
        self.assertEqual(len(migrated.status_flow), 3)
        self.assertEqual(migrated.status_flow[1]["date"], "not-a-date")

    @staticmethod
    def _legacy_document(apps):
        cover_page = apps.get_model("common", "CoverPage").objects.create(
            project_slug="ozgur", number="CP-MIGRATION"
        )
        return apps.get_model("ozgur", "CompDoc").objects.create(
            name="Migration document",
            cover_page=cover_page,
            cover_page_no=cover_page.number,
            status_flow=[
                {"status": "to_be_issued", "date": "01.01.2026"},
                {"status": "authority_review", "date": "not-a-date"},
                {"status": "authority_approved", "date": "03.01.2026"},
            ],
        )
