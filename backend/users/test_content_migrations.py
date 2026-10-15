"""Fresh schemas store owner content separately from appearance preferences."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import JSONField, Value
from django.test import TestCase

from integrations.models import JiraUserContent
from word.models import DocumentAnalysisUserContent
from .models import UserPreferences


class FreshUserContentSchemaTests(TestCase):
    def test_owner_content_round_trips_without_legacy_preference_columns(self):
        payloads = [
            ([{"title": "Saved draft", "list": [{"summary": ""}]}],
             [{"question": "Keep exactly?"}]),
            ({"preserve": True}, []),
            (None, None),
        ]
        for index, (lists, checks) in enumerate(payloads):
            with self.subTest(payload=index):
                owner = get_user_model().objects.create_user(f"baseline-content-{index}")
                JiraUserContent.objects.create(
                    user=owner, subtask_lists=Value(lists, output_field=JSONField()),
                )
                DocumentAnalysisUserContent.objects.create(
                    user=owner, checks=Value(checks, output_field=JSONField()),
                )
                preferences = owner.preferences
                preferences.theme = "dark"
                preferences.save(update_fields=["theme"])
                self.assertEqual(JiraUserContent.objects.get(user=owner).subtask_lists, lists)
                self.assertEqual(DocumentAnalysisUserContent.objects.get(user=owner).checks, checks)
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(
                cursor, UserPreferences._meta.db_table,
            )}
        self.assertNotIn("jira_list", columns)
        self.assertNotIn("document_analysis_checks", columns)
        self.assertIn("version", columns)
