from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from orgs.models import Project
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
