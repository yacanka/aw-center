from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from rest_framework.test import APIClient

from orgs.models import People, Project
from projects.registry import PROJECT_DEFINITIONS, get_enabled_project_definitions


class SyncProjectsCommandTests(TestCase):
    """Verify registry-to-org project synchronization behavior."""

    def call_sync_projects(self, *arguments):
        """Run sync_projects and return its stdout."""
        output = StringIO()
        call_command("sync_projects", *arguments, stdout=output)
        return output.getvalue()

    def test_creates_missing_enabled_projects(self):
        """The command creates enabled registry projects by default."""
        output = self.call_sync_projects()

        expected_slugs = {definition.slug for definition in get_enabled_project_definitions()}
        self.assertEqual(Project.objects.count(), len(expected_slugs))
        self.assertEqual(set(Project.objects.values_list("slug", flat=True)), expected_slugs)
        self.assertIn("created=6", output)
        self.assertIn("skipped_disabled=2", output)

    def test_existing_projects_are_no_op_by_default(self):
        """Existing user-edited project names are preserved by default."""
        Project.objects.create(slug="ozgur", name="Custom Ozgur")

        output = self.call_sync_projects()

        self.assertEqual(Project.objects.get(slug="ozgur").name, "Custom Ozgur")
        self.assertIn("UNCHANGED ozgur: existing name preserved", output)

    def test_dry_run_does_not_create_projects(self):
        """Dry-run reports planned creates without database writes."""
        output = self.call_sync_projects("--dry-run")

        self.assertFalse(Project.objects.exists())
        self.assertIn("CREATE ozgur: Ozgur", output)
        self.assertIn("DRY RUN created=6", output)

    def test_update_display_name_flag_updates_existing_projects(self):
        """The explicit update flag synchronizes existing display names."""
        Project.objects.create(slug="aesa", name="User AESA")

        output = self.call_sync_projects("--update-display-name")

        self.assertEqual(Project.objects.get(slug="aesa").name, "AESA")
        self.assertIn("UPDATE aesa: User AESA -> AESA", output)

    def test_include_disabled_flag_creates_disabled_projects(self):
        """Disabled registry projects are only created when requested."""
        output = self.call_sync_projects("--include-disabled")

        self.assertEqual(Project.objects.count(), len(PROJECT_DEFINITIONS))
        self.assertTrue(Project.objects.filter(slug="gokbey").exists())
        self.assertIn("skipped_disabled=0", output)


class PeopleApiTests(TestCase):
    """Verify people API authentication, search, and pagination behavior."""

    def setUp(self):
        """Create an authenticated API client and representative people rows."""
        user = get_user_model().objects.create_user(username="architect", password="secret")
        self.client = APIClient()
        self.client.force_authenticate(user=user)
        People.objects.bulk_create(
            [
                People(person_id="100001", name="Ada Lovelace", email="ada@example.com"),
                People(person_id="100002", name="Grace Hopper", email="grace@example.com"),
                People(person_id="100003", name="Alan Turing", email="alan@example.com"),
            ]
        )

    def test_people_list_uses_drf_pagination(self):
        """People list responses expose count and results for remote tables."""
        response = self.client.get("/orgs/people/", {"page_size": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)

    def test_people_search_filters_by_name(self):
        """The search query limits results to matching person names."""
        response = self.client.get("/orgs/people/", {"search": "Grace"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["person_id"], "100002")

    def test_people_list_requires_authentication(self):
        """Anonymous clients cannot pull people data from the login screen."""
        anonymous_client = APIClient()

        response = anonymous_client.get("/orgs/people/")

        self.assertEqual(response.status_code, 401)
