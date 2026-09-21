"""Read-only project catalog/database alignment command tests."""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from orgs.models import Project


class ProjectRegistryDatabaseAlignmentTests(TestCase):
    def test_seeded_catalog_passes(self):
        call_command("check_project_registry")

    def test_hurjet_is_seeded_with_its_business_name(self):
        project = Project.objects.get(slug="hurjet")

        self.assertEqual(project.name, "Hürjet")
        self.assertTrue(project.enabled)

    def test_missing_catalog_project_fails(self):
        Project.objects.filter(slug="ozgur").delete()
        with self.assertRaisesMessage(CommandError, "ozgur"):
            call_command("check_project_registry")

    def test_unknown_database_project_is_only_reported(self):
        Project.objects.create(name="Unknown", slug="unknown")
        stderr = StringIO()
        call_command("check_project_registry", stderr=stderr)
        self.assertIn("unknown", stderr.getvalue())

    def test_new_dcc_projects_are_seeded_without_replacing_gokbey(self):
        for slug in ("gokbey", "gokbey_jandarma", "gokbey_sivil", "hurkus"):
            self.assertTrue(Project.objects.get(slug=slug).enabled)
        self.assertEqual(Project.objects.get(slug="ozgur").name, "Özgür")
