"""Fresh installs own the current schema without retired application identities."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from compliance.models import ComplianceDocument, DocumentStatus
from integrations.models import JiraTrackedIssue
from orgs.models import Project
from projects.registry import PROJECT_DEFINITIONS


class FreshMigrationBaselineTests(TestCase):
    def test_jira_schema_has_no_dependency_on_retired_application(self):
        loader = MigrationLoader(connection)
        self.assertFalse(apps.is_installed("integrations.jira.legacy_dcc"))
        self.assertFalse(any(label == "dcc" for label, _ in loader.graph.nodes))
        self.assertFalse(ContentType.objects.filter(app_label="dcc").exists())
        permission = Permission.objects.get(
            content_type__app_label="integrations", codename="view_jiratrackedissue",
        )
        self.assertEqual(permission.content_type.model_class(), JiraTrackedIssue)

    def test_fresh_install_seeds_catalog_and_only_unknown_statuses(self):
        self.assertEqual(set(Project.objects.values_list("slug", flat=True)), set(PROJECT_DEFINITIONS))
        for project in Project.objects.all():
            with self.subTest(project=project.slug):
                self.assertEqual(list(DocumentStatus.objects.filter(project=project).values_list(
                    "value", "label",
                )), [("unknown", "Unknown")])
        self.assertEqual(Project.objects.get(slug="ozgur").name, "Özgür")
        self.assertEqual(Project.objects.get(slug="gokbey").name, "Gökbey")
        self.assertEqual(Project.objects.get(slug="hurjet").name, "Hürjet")

    def test_current_document_columns_exist_in_live_and_history_tables(self):
        for model in (ComplianceDocument, ComplianceDocument.history.model):
            with self.subTest(model=model._meta.label):
                with connection.cursor() as cursor:
                    columns = {column.name for column in connection.introspection.get_table_description(
                        cursor, model._meta.db_table,
                    )}
                self.assertTrue({"number", "issue", "target_date", "revised_target_date", "release_date"} <= columns)
                self.assertFalse({
                    "tech_doc_no", "tech_doc_issue", "ubm_target_date", "ubm_revised_target_date",
                    "ubm_delivery_date", "tech_doc_no_2", "tech_doc_issue_2",
                    "delivered_tech_doc_issue", "delivered_tech_doc_issue_2",
                } & columns)

    def test_fresh_jira_relations_use_canonical_models_and_enforce_uniqueness(self):
        owner = get_user_model().objects.create_user("baseline-owner")
        assignee = get_user_model().objects.create_user("baseline-assignee")
        project = Project.objects.get(slug="ozgur")
        record = JiraTrackedIssue.objects.create(owner=owner, issue="BASELINE-1", title="Tracked issue")
        record.assigned_users.add(assignee)
        record.projects.add(project)
        record.refresh_from_db()
        self.assertEqual(list(record.assigned_users.values_list("pk", flat=True)), [assignee.pk])
        self.assertEqual(list(record.projects.values_list("pk", flat=True)), [project.pk])
        self.assertEqual(record._meta.app_label, "integrations")
        with self.assertRaises(IntegrityError), transaction.atomic():
            record.assigned_users.through.objects.create(issue=record, user=assignee)
        with self.assertRaises(IntegrityError), transaction.atomic():
            record.projects.through.objects.create(issue=record, project=project)
