"""Content migration must preserve payloads and identifiers without normalization."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import JSONField, Value
from django.test import TransactionTestCase


class UserContentMigrationTests(TransactionTestCase):
    def test_content_is_copied_exactly_before_old_fields_are_removed(self):
        self.addCleanup(self.restore_latest)
        executor = MigrationExecutor(connection)
        before = [("users", "0002_userpreferences_version")]
        executor.migrate(before)
        old = executor.loader.project_state(before).apps
        User = old.get_model("auth", "User")
        Preferences = old.get_model("users", "UserPreferences")
        lists = [{"title": "Saved draft", "list": [{"summary": ""}]}]
        checks = [{"id": "71c5c4fa-995d-4f65-9e60-c2dfd7d22f1b", "question": "Keep exactly?"}]
        owner = User.objects.create(username="content-migration")
        Preferences.objects.create(user_id=owner.pk, jira_list=lists, document_analysis_checks=checks)
        malformed = User.objects.create(username="malformed-content-migration")
        Preferences.objects.create(user_id=malformed.pk, jira_list={"preserve": True}, document_analysis_checks=[])
        null_owner = User.objects.create(username="json-null-migration")
        Preferences.objects.create(user_id=null_owner.pk, jira_list=Value(None, output_field=JSONField()),
                                   document_analysis_checks=Value(None, output_field=JSONField()))
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            new = executor.loader.project_state().apps
            Jira = new.get_model("integrations", "JiraUserContent")
            Analysis = new.get_model("word", "DocumentAnalysisUserContent")
            self.assertEqual(Jira.objects.get(pk=owner.pk).subtask_lists, lists)
            self.assertEqual(Analysis.objects.get(pk=owner.pk).checks, checks)
            self.assertEqual(Jira.objects.get(pk=malformed.pk).subtask_lists, {"preserve": True})
            self.assertIsNone(Jira.objects.get(pk=null_owner.pk).subtask_lists)
            self.assertIsNone(Analysis.objects.get(pk=null_owner.pk).checks)
            self.assertNotIn("jira_list", {field.name for field in new.get_model("users", "UserPreferences")._meta.fields})
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def restore_latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
