"""Legacy import must tolerate old preference schemas and keep per-account atomicity."""

from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, connections
from django.test import SimpleTestCase, TestCase
from users.management.commands.copy_users import USER_COPY_FIELDS, get_legacy_preference_values
from users.models import UserPreferences


class LegacyPreferenceSchemaTests(SimpleTestCase):
    def test_reads_only_available_columns_and_decodes_json(self):
        connection = MagicMock()
        connection.introspection.table_names.return_value = ["user_preferences"]
        connection.introspection.get_table_description.return_value = [
            SimpleNamespace(name=name) for name in ("user_id", "theme", "jira_list")
        ]
        connection.ops.quote_name.side_effect = lambda name: f'"{name}"'
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("dark", '[{"summary": "Example"}]')
        with patch("users.management.commands.copy_users.connections", {"db_old": connection}):
            values = get_legacy_preference_values(7)
        self.assertEqual(values, {"theme": "dark", "jira_list": [{"summary": "Example"}]})
        sql, parameters = cursor.execute.call_args.args
        self.assertNotIn("document_analysis_checks", sql)
        self.assertEqual(parameters, [7])

    def test_missing_preferences_table_is_supported(self):
        connection = MagicMock()
        connection.introspection.table_names.return_value = []
        with patch("users.management.commands.copy_users.connections", {"db_old": connection}):
            self.assertIsNone(get_legacy_preference_values(7))


class CopyUsersTests(TestCase):
    @contextmanager
    def legacy_source(self, users, preferences):
        original_using = User.objects.using
        source = MagicMock()
        source.all.return_value.iterator.return_value = iter(users)
        with (
            patch.object(User.objects, "using", side_effect=lambda alias: source if alias == "db_old" else original_using(alias)),
            patch("users.management.commands.copy_users.connections", {
                "db_old": SimpleNamespace(settings_dict={"NAME": "legacy-import-fixture"}),
                "default": connections["default"],
            }),
            patch("users.management.commands.copy_users.get_legacy_preference_values", return_value=preferences),
        ):
            yield

    def legacy_user(self, username):
        user = User(username=username, email="fixture@example.invalid", is_active=True)
        user.set_unusable_password()
        return SimpleNamespace(pk=701, username=username, **{field: getattr(user, field) for field in USER_COPY_FIELDS})

    def test_imports_preferences_and_keeps_new_column_defaults(self):
        with self.legacy_source([self.legacy_user("imported")], {"theme": "dark", "jira_list": []}):
            call_command("copy_users", stdout=StringIO())
        user = User.objects.get(username="imported")
        self.assertEqual(user.preferences.theme, "dark")
        self.assertEqual(user.preferences.document_analysis_checks, [])
        self.assertFalse(user.has_usable_password())

    def test_existing_account_changes_require_explicit_option(self):
        user = User.objects.create_user("existing", email="current@example.invalid")
        for update in (False, True):
            with self.legacy_source([self.legacy_user("existing")], {"theme": "dark"}):
                call_command("copy_users", update_existing=update, stdout=StringIO())
            user.refresh_from_db()
            self.assertEqual(user.email, "fixture@example.invalid" if update else "current@example.invalid")
            self.assertEqual(UserPreferences.objects.get(user=user).theme, "dark")

    def test_preference_conflict_rolls_back_account_and_does_not_log_details(self):
        output, errors = StringIO(), StringIO()
        from django.db.models.query import QuerySet
        with (
            self.legacy_source([self.legacy_user("rollback")], {"theme": "dark"}),
            patch.object(QuerySet, "update_or_create", side_effect=IntegrityError("private diagnostic")),
        ):
            call_command("copy_users", stdout=output, stderr=errors)
        self.assertFalse(User.objects.filter(username="rollback").exists())
        self.assertIn("0 users copied", output.getvalue())
        self.assertNotIn("private diagnostic", errors.getvalue())
