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


class RegisteredProjectsApiTests(TestCase):
    """Verify Organizations exposes the central registry as read-only data."""

    def setUp(self):
        """Create an authenticated client for the protected registry alias."""
        user = get_user_model().objects.create_user(username="org-admin", password="secret")
        self.client = APIClient()
        self.client.force_authenticate(user=user)

    def test_project_list_comes_from_registry_without_database_rows(self):
        """Registered projects are visible even when orgs.Project is empty."""
        response = self.client.get("/orgs/projects/", {"capability": "orgs"})

        expected_slugs = {
            definition.slug
            for definition in PROJECT_DEFINITIONS.values()
            if "orgs" in definition.capabilities
        }
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertEqual({item["slug"] for item in response.data}, expected_slugs)

    def test_project_collection_rejects_mutation(self):
        """Clients cannot create projects outside the backend registry."""
        response = self.client.post("/orgs/projects/", {"name": "Unregistered"})

        self.assertEqual(response.status_code, 405)


class ProjectOrganizationApiTests(TestCase):
    """Verify project-specific panel and responsible query contracts."""

    def setUp(self):
        """Create one project panel and responsibles with distinct ATA chapters."""
        from projects.ozgur.models import Panel, Responsible

        user = get_user_model().objects.create_user(username="org-user", password="secret")
        self.client = APIClient()
        self.client.force_authenticate(user=user)
        first_panel = Panel.objects.create(name="Avionics", discipline="System", ata="21-00")
        second_panel = Panel.objects.create(name="Propulsion", discipline="System", ata="72-00")
        Responsible.objects.create(
            panel=first_panel,
            person_id="100001",
            name="Ada Engineer",
            email="ada@example.com",
            title="AS",
        )
        Responsible.objects.create(
            panel=second_panel,
            person_id="100002",
            name="Grace Engineer",
            email="grace@example.com",
            title="CVE",
        )

    def test_responsibles_are_filtered_by_panel_ata(self):
        """The frontend panel value is an ATA chapter, not a panel name."""
        response = self.client.get("/ozgur/orgs/responsibles/", {"panel": "21-00"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["person_id"], "100001")


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
                People(person_id="100004", name="Grace Murray", email="murray@example.com"),
            ]
        )

    def test_people_list_uses_drf_pagination(self):
        """People list responses expose count and results for remote tables."""
        response = self.client.get("/orgs/people/", {"page_size": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(len(response.data["results"]), 2)

    def test_people_search_filters_by_name(self):
        """The search query limits results to matching person names."""
        response = self.client.get("/orgs/people/", {"search": "Hopper"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["person_id"], "100002")

    def test_people_search_ranks_exact_name_before_other_matches(self):
        """Exact and prefix matches lead less similar directory results."""
        response = self.client.get("/orgs/people/", {"search": "Grace", "page_size": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["person_id"], "100002")

    def test_people_search_supports_typo_and_server_pagination(self):
        """A bounded fuzzy search remains inside the shared pagination contract."""
        response = self.client.get("/orgs/people/", {"search": "Grce", "page_size": 1})

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["person_id"], "100002")

    def test_people_search_preserves_rank_across_dropdown_pages(self):
        """Following pages continue the same deterministic similarity ordering."""
        first = self.client.get("/orgs/people/", {"search": "Grce", "page_size": 1})
        second = self.client.get(
            "/orgs/people/",
            {"search": "Grce", "page_size": 1, "page": 2},
        )

        self.assertEqual(first.data["count"], 2)
        self.assertIsNotNone(first.data["next"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["count"], 2)
        self.assertEqual(second.data["results"][0]["person_id"], "100004")
        self.assertIsNone(second.data["next"])

    def test_direct_search_count_is_not_fuzzy_candidate_limited(self):
        """Ordinary server-filtered results retain an exact pagination count."""
        People.objects.bulk_create(
            [
                People(person_id=str(200000 + index), name=f"Engineer {index}", email=f"e{index}@x.io")
                for index in range(501)
            ]
        )

        response = self.client.get("/orgs/people/", {"search": "Engineer", "page_size": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 501)
        self.assertEqual(len(response.data["results"]), 2)

    def test_people_search_matches_email_and_person_id(self):
        """Lookup fields are searchable without downloading the directory."""
        email_response = self.client.get("/orgs/people/", {"search": "alan@example.com"})
        id_response = self.client.get("/orgs/people/", {"search": "100001"})

        self.assertEqual(email_response.data["results"][0]["person_id"], "100003")
        self.assertEqual(id_response.data["results"][0]["name"], "Ada Lovelace")

    def test_people_search_rejects_unbounded_input(self):
        """Oversized search terms cannot trigger expensive fuzzy work."""
        response = self.client.get("/orgs/people/", {"search": "x" * 101})

        self.assertEqual(response.status_code, 400)
        self.assertIn("search", response.data["errors"])

    def test_people_list_requires_authentication(self):
        """Anonymous clients cannot pull people data from the login screen."""
        anonymous_client = APIClient()

        response = anonymous_client.get("/orgs/people/")

        self.assertEqual(response.status_code, 401)
