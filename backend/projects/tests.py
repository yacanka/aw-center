"""Tests for the project registry metadata."""

from importlib import import_module
from types import MappingProxyType
from unittest import TestCase

from django.urls import URLResolver

from awcenter.urls import urlpatterns

from .registry import (
    PROJECT_DEFINITIONS,
    UnknownProjectDefinitionError,
    find_project_by_jira_component,
    get_enabled_project_definitions,
    get_project_definition,
    get_project_definitions_by_capability,
)

KNOWN_CAPABILITIES = {"dcc", "compdocs", "orgs"}


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

    def test_registry_slugs_are_unique(self):
        """Every declared project slug is globally unique."""
        declared_slugs = [definition.slug for definition in PROJECT_DEFINITIONS.values()]

        self.assertEqual(len(declared_slugs), len(set(declared_slugs)))

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
                self.assertTrue(definition.capabilities)
                self.assertTrue(definition.tags)

    def test_project_app_labels_are_importable(self):
        """Every project app label points to an importable project package."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            with self.subTest(slug=slug):
                module = import_module(f"projects.{definition.app_label}")

                self.assertIsNotNone(module)

    def test_enabled_project_definitions_have_url_prefix(self):
        """Enabled project definitions always expose a non-empty URL prefix."""
        for definition in get_enabled_project_definitions():
            with self.subTest(slug=definition.slug):
                self.assertTrue(definition.url_prefix.strip())

    def test_project_capabilities_are_known_values(self):
        """Project capabilities are constrained to supported feature flags."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            with self.subTest(slug=slug):
                self.assertTrue(set(definition.capabilities) <= KNOWN_CAPABILITIES)

    def test_dcc_project_definitions_have_dcc_metadata(self):
        """Every DCC-capable project includes DCC-safe identifiers."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            if "dcc" not in definition.capabilities:
                continue

            with self.subTest(slug=slug):
                self.assertTrue(definition.jira_component)
                self.assertTrue(definition.dcc_label)
                self.assertTrue(definition.dcc_template_name)

    def test_inactive_projects_are_disabled(self):
        """Inactive project applications stay disabled in the registry."""
        self.assertFalse(PROJECT_DEFINITIONS["blok4050"].enabled)
        self.assertFalse(PROJECT_DEFINITIONS["gokbey"].enabled)

    def test_disabled_projects_are_excluded_from_url_generation(self):
        """Disabled projects remain registered but are not included in URLs."""
        project_prefixes = self.get_project_url_prefixes()

        self.assertIn("blok4050", PROJECT_DEFINITIONS)
        self.assertIn("gokbey", PROJECT_DEFINITIONS)
        self.assertNotIn("blok4050", project_prefixes)
        self.assertNotIn("gokbey", project_prefixes)

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
        enabled_slugs = {definition.slug for definition in get_enabled_project_definitions()}

        self.assertIn("ozgur", enabled_slugs)
        self.assertNotIn("blok4050", enabled_slugs)
        self.assertNotIn("gokbey", enabled_slugs)

    def test_get_project_definitions_by_capability_returns_enabled_matches(self):
        """Capability lookup returns enabled projects only."""
        dcc_slugs = {
            definition.slug for definition in get_project_definitions_by_capability(" DCC ")
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

    def get_project_url_prefixes(self):
        """Return configured project URL prefixes from the root URL patterns."""
        registry_prefixes = {
            definition.url_prefix for definition in PROJECT_DEFINITIONS.values()
        }
        return {
            str(pattern.pattern).strip("/")
            for pattern in urlpatterns
            if isinstance(pattern, URLResolver)
            and str(pattern.pattern).strip("/") in registry_prefixes
        }
