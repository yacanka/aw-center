"""Exercise the field transition against real pre-refactor database rows."""

from datetime import date
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class CanonicalDocumentMigrationTests(TransactionTestCase):
    migrate_from = [("compliance", "0015_seed_compliance_project_statuses")]
    migrate_to = [("compliance", "0016_canonical_document_fields")]

    def test_preserves_primary_and_history_values_and_updates_saved_doors_mapping(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self.restore_latest_schema)
        old = executor.loader.project_state(self.migrate_from).apps
        project, _ = old.get_model("orgs", "Project").objects.get_or_create(
            slug="ozgur", defaults={"name": "Ozgur"},
        )
        cover = old.get_model("compliance", "CoverPage").objects.create(
            project_id=project.pk, number="CP-MIGRATION", issue="C",
        )
        values = {
            "id": uuid4(), "project_id": project.pk, "cover_page_id": cover.pk,
            "name": "Migration document", "tech_doc_no": "TD-MIGRATION", "tech_doc_issue": "B",
            "ubm_target_date": date(2026, 10, 1),
            "ubm_revised_target_date": date(2026, 11, 1),
            "ubm_delivery_date": date(2026, 9, 1), "version": 7,
            "tech_doc_no_2": "REMOVED", "tech_doc_issue_2": "X",
            "delivered_tech_doc_issue": "Y", "delivered_tech_doc_issue_2": "Z",
        }
        old.get_model("compliance", "ComplianceDocument").objects.create(**values)
        old.get_model("compliance", "HistoricalComplianceDocument").objects.create(
            **values, updated_at=timezone.now(), history_date=timezone.now(), history_type="~",
        )
        mapping = old.get_model("compliance", "DoorsImportMapping").objects.create(
            project_id=project.pk, module_path="/Migration module", successful_at=timezone.now(),
            mapping={
                "Title": "name", "No": "tech_doc_no", "Issue": "tech_doc_issue",
                "Target": "ubm_target_date", "Revised": "ubm_revised_target_date",
                "Released": "ubm_delivery_date", "Secondary": "tech_doc_no_2",
                "Secondary issue": "tech_doc_issue_2", "Delivered": "delivered_tech_doc_issue",
                "Delivered 2": "delivered_tech_doc_issue_2",
            },
            source_columns=["Title", "No", "Secondary"],
        )
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        current = executor.loader.project_state(self.migrate_to).apps
        for model_name in ("ComplianceDocument", "HistoricalComplianceDocument"):
            model = current.get_model("compliance", model_name)
            row = model.objects.get(id=values["id"])
            self.assertEqual(row.number, "TD-MIGRATION")
            self.assertEqual(row.issue, "B")
            self.assertEqual(row.target_date, date(2026, 10, 1))
            self.assertEqual(row.revised_target_date, date(2026, 11, 1))
            self.assertEqual(row.release_date, date(2026, 9, 1))
            self.assertEqual(row.version, 7)
            with connection.cursor() as cursor:
                columns = {col.name for col in connection.introspection.get_table_description(cursor, model._meta.db_table)}
            self.assertFalse({"tech_doc_no_2", "tech_doc_issue_2", "delivered_tech_doc_issue", "delivered_tech_doc_issue_2"} & columns)
        saved = current.get_model("compliance", "DoorsImportMapping").objects.get(pk=mapping.pk)
        self.assertEqual(saved.mapping, {
            "Title": "name", "No": "number", "Issue": "issue", "Target": "target_date",
            "Revised": "revised_target_date", "Released": "release_date",
        })
        self.assertEqual(saved.source_columns, ["Title", "No", "Secondary"])
        self.assertEqual(saved.successful_at, mapping.successful_at)

    def test_refuses_transition_with_unfinished_numbering_snapshot(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self.restore_latest_schema)
        old = executor.loader.project_state(self.migrate_from).apps
        project, _ = old.get_model("orgs", "Project").objects.get_or_create(
            slug="ozgur", defaults={"name": "Ozgur"},
        )
        user = old.get_model("auth", "User").objects.create(username="migration-actor")
        allocations = old.get_model("compliance", "CoverPageNumberAllocation").objects
        allocation = allocations.create(
            project_id=project.pk, actor_id=user.pk, client_operation_id=uuid4(),
            request_hash="a" * 64, credential_fingerprint="test",
            format_code="TEST", document_snapshot={"tech_doc_no": "TD-PENDING"},
            status="requested",
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "unfinished cover page"):
                MigrationExecutor(connection).migrate(self.migrate_to)
        finally:
            allocations.filter(pk=allocation.pk).update(status="completed")

    def restore_latest_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
