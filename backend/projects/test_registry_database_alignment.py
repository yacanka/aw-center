"""Tests for read-only project registry/database alignment checks."""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from orgs.models import Project
from projects.registry import PROJECT_DEFINITIONS, get_enabled_project_definitions


class ProjectRegistryDatabaseAlignmentTests(TestCase):
    """Validate orgs.Project slug alignment with enabled registry definitions."""

    def test_command_passes_when_enabled_registry_projects_exist(self):
        """Every enabled registry slug must have a matching orgs.Project row."""
        self.create_enabled_registry_projects()

        call_command("check_project_registry")

    def test_command_fails_when_enabled_registry_project_is_missing(self):
        """Missing enabled registry project rows produce a non-destructive failure."""
        first_definition = get_enabled_project_definitions()[0]

        with self.assertRaisesMessage(CommandError, first_definition.slug):
            call_command("check_project_registry")

    def test_command_warns_for_database_project_missing_from_registry(self):
        """Database-only project rows are reported without deleting them."""
        self.create_enabled_registry_projects()
        Project.objects.create(name="Legacy Project", slug="legacy")

        stderr = StringIO()

        call_command("check_project_registry", stderr=stderr)

        self.assertIn("legacy", stderr.getvalue())
        self.assertTrue(Project.objects.filter(slug="legacy").exists())

    def create_enabled_registry_projects(self):
        """Create the minimal orgs.Project rows required by enabled definitions."""
        for definition in get_enabled_project_definitions():
            Project.objects.create(name=definition.display_name, slug=definition.slug)

    def test_project_model_stays_free_of_registry_technical_fields(self):
        """orgs.Project remains business data, not a registry implementation mirror."""
        project_fields = {field.name for field in Project._meta.fields}
        forbidden_fields = {"app_label", "serializer_path", "model_path"}

        self.assertTrue(forbidden_fields.isdisjoint(project_fields))
        self.assertTrue(PROJECT_DEFINITIONS)
