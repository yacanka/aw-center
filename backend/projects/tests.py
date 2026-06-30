"""Tests for the project registry metadata."""

from types import MappingProxyType
from unittest import TestCase

from .registry import PROJECT_DEFINITIONS


class ProjectRegistryTests(TestCase):
    """Validate required project registry invariants."""

    def test_registry_contains_expected_project_definitions(self):
        """Registry includes the known project applications."""
        expected_slugs = {
            "ozgur",
            "piku",
            "aesa",
            "havasoj",
            "hys",
            "blok30",
            "blok4050",
            "gokbey",
        }

        self.assertEqual(set(PROJECT_DEFINITIONS), expected_slugs)

    def test_registry_is_read_only(self):
        """Registry mapping cannot be modified at runtime."""
        self.assertIsInstance(PROJECT_DEFINITIONS, MappingProxyType)

        with self.assertRaises(TypeError):
            PROJECT_DEFINITIONS["temporary"] = PROJECT_DEFINITIONS["ozgur"]

    def test_registry_definitions_have_required_metadata(self):
        """Every project definition includes required metadata."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            with self.subTest(slug=slug):
                self.assertEqual(definition.slug, slug)
                self.assertTrue(definition.display_name)
                self.assertTrue(definition.app_label)
                self.assertTrue(definition.url_prefix)
                self.assertTrue(definition.capabilities)
                self.assertTrue(definition.tags)

    def test_dcc_project_definitions_have_dcc_metadata(self):
        """Every DCC-capable project includes DCC-safe identifiers."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            with self.subTest(slug=slug):
                self.assertIn("dcc", definition.capabilities)
                self.assertTrue(definition.jira_component)
                self.assertTrue(definition.dcc_label)
                self.assertTrue(definition.dcc_template_name)
                self.assertTrue(definition.mail_template_name)

    def test_inactive_projects_are_disabled(self):
        """Inactive project applications stay disabled in the registry."""
        self.assertFalse(PROJECT_DEFINITIONS["blok4050"].enabled)
        self.assertFalse(PROJECT_DEFINITIONS["gokbey"].enabled)
