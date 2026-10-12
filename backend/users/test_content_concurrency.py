"""Separate database connections exercise SQLite/PG version fencing."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase

from awcenter.database_errors import ContentConflict
from integrations.jira.user_content import get_saved_lists, replace_saved_lists
from integrations.jira.preferences import update_jira_preferences
from users.preference_service import reset_appearance
from word.custom_checks import create_custom_check, get_custom_checks


class UserContentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("concurrent-owner")

    def race(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                try:
                    return operation(user)
                except ContentConflict as error:
                    return error
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(run, operations))

    def test_two_first_writes_have_one_winner_without_overwriting(self):
        results = self.race([lambda user: replace_saved_lists(user, [{"title": "One", "list": []}], version=0),
                             lambda user: replace_saved_lists(user, [{"title": "Two", "list": []}], version=0)])
        self.assertEqual(sum(isinstance(result, ContentConflict) for result in results), 1)
        self.assertEqual(get_saved_lists(self.user)["version"], 1)
        winner = next(result for result in results if not isinstance(result, ContentConflict))
        self.assertEqual(get_saved_lists(self.user), winner)

    def test_concurrent_questions_and_reset_preserve_content(self):
        self.race([lambda user: create_custom_check(user, "First question?"),
                   lambda user: create_custom_check(user, "Second question?"),
                   reset_appearance])
        self.assertEqual({check["question"] for check in get_custom_checks(self.user)},
                         {"First question?", "Second question?"})

    def test_two_project_preferences_preserve_both_selections(self):
        self.race([lambda user: update_jira_preferences(user, {"project_slug": "hys", "detail_field_ids": ["priority"]}),
                   lambda user: update_jira_preferences(user, {"project_slug": "gokbey", "detail_field_ids": ["status"]})])
        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.extra_settings["watcher"]["detail_fields"],
                         {"hys": ["priority"], "gokbey": ["status"]})
