"""Tests for the project registry metadata."""

from importlib import import_module
from types import MappingProxyType
from unittest import TestCase

from .registry import (
    PROJECT_DEFINITIONS,
    UnknownProjectDefinitionError,
    find_project_by_jira_component,
    get_enabled_project_definitions,
    get_project_definition,
    get_project_definitions_by_capability,
)


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

    def test_get_project_definition_returns_registered_definition(self):
        """Slug lookup is case-insensitive and ignores surrounding whitespace."""
        definition = get_project_definition(" OZGUR ")

        self.assertEqual(definition.slug, "ozgur")

    def test_get_project_definition_raises_for_unknown_slug(self):
        """Unknown required project slugs fail with a controlled exception."""
        with self.assertRaises(UnknownProjectDefinitionError):
            get_project_definition("unknown")

    def test_get_enabled_project_definitions_excludes_disabled_projects(self):
        """Enabled project lookup returns only active registry entries."""
        enabled_slugs = {
            definition.slug for definition in get_enabled_project_definitions()
        }

        self.assertIn("ozgur", enabled_slugs)
        self.assertNotIn("blok4050", enabled_slugs)
        self.assertNotIn("gokbey", enabled_slugs)

    def test_get_project_definitions_by_capability_returns_enabled_matches(self):
        """Capability lookup returns enabled projects only."""
        dcc_slugs = {
            definition.slug
            for definition in get_project_definitions_by_capability(" DCC ")
        }

        self.assertIn("piku", dcc_slugs)
        self.assertNotIn("gokbey", dcc_slugs)

    def test_find_project_by_jira_component_returns_enabled_match(self):
        """JIRA component lookup is case-insensitive and enabled-only."""
        definition = find_project_by_jira_component(" aesa ")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.slug, "aesa")

    def test_find_project_by_jira_component_returns_none_for_unknown_component(self):
        """Unknown or disabled JIRA components use an explicit None strategy."""
        self.assertIsNone(find_project_by_jira_component("unknown"))
        self.assertIsNone(find_project_by_jira_component("GOKBEY"))

    def test_registry_app_labels_expose_importable_url_modules(self):
        """Enabled project app labels resolve to URL modules during routing setup."""
        for definition in get_enabled_project_definitions():
            with self.subTest(slug=definition.slug):
                import_module(f"{definition.app_label}.urls")

    def test_get_project_urlpatterns_excludes_disabled_projects(self):
        """Project route helper emits URL patterns only for enabled projects."""
        from .routing import get_project_urlpatterns

        route_names = {str(pattern.pattern) for pattern in get_project_urlpatterns()}

        self.assertIn("ozgur/", route_names)
        self.assertIn("blok30/", route_names)
        self.assertNotIn("blok4050/", route_names)
        self.assertNotIn("gokbey/", route_names)
