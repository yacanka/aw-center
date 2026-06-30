"""Project registry invariant tests."""

from importlib import import_module
from unittest import TestCase

from django.urls import URLResolver

from awcenter.urls import urlpatterns

from .constants import ALLOWED_PROJECT_CAPABILITIES, PROJECT_CAPABILITY_DCC
from .registry import PROJECT_DEFINITIONS, get_enabled_project_definitions


class ProjectRegistryInvariantTests(TestCase):
    """Validate project registry invariants that protect route generation."""

    def test_registry_slugs_are_unique(self):
        """Every declared project slug is globally unique."""
        declared_slugs = [definition.slug for definition in PROJECT_DEFINITIONS.values()]

        self.assertEqual(len(declared_slugs), len(set(declared_slugs)))

    def test_project_app_labels_are_importable(self):
        """Every project app label points to an importable project package."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            with self.subTest(slug=slug):
                module = import_module(f"projects.{definition.app_label}")

                self.assertIsNotNone(module)

    def test_enabled_project_definitions_have_url_prefix(self):
        """Every enabled project definition exposes a non-empty URL prefix."""
        for definition in get_enabled_project_definitions():
            with self.subTest(slug=definition.slug):
                self.assertTrue(definition.url_prefix.strip())

    def test_project_capabilities_are_known_values(self):
        """Every declared capability is part of the supported capability set."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            with self.subTest(slug=slug):
                unknown_capabilities = set(definition.capabilities) - ALLOWED_PROJECT_CAPABILITIES

                self.assertEqual(unknown_capabilities, set())

    def test_dcc_project_definitions_have_required_metadata(self):
        """DCC-capable projects include required DCC metadata identifiers."""
        for slug, definition in PROJECT_DEFINITIONS.items():
            if PROJECT_CAPABILITY_DCC not in definition.capabilities:
                continue

            with self.subTest(slug=slug):
                self.assertTrue(definition.jira_component)
                self.assertTrue(definition.dcc_label)
                self.assertTrue(definition.dcc_template_name)

    def test_disabled_projects_are_excluded_from_url_generation(self):
        """Disabled projects remain registered but are excluded from URLs."""
        disabled_definitions = self.get_disabled_project_definitions()
        generated_prefixes = self.get_generated_project_url_prefixes()

        self.assertTrue(disabled_definitions)
        for definition in disabled_definitions:
            with self.subTest(slug=definition.slug):
                self.assertNotIn(definition.url_prefix, generated_prefixes)

    def get_disabled_project_definitions(self):
        """Return project definitions that are registered as disabled."""
        return [
            definition
            for definition in PROJECT_DEFINITIONS.values()
            if not definition.enabled
        ]

    def get_generated_project_url_prefixes(self):
        """Return project route prefixes currently mounted by Django."""
        registry_prefixes = {
            definition.url_prefix for definition in PROJECT_DEFINITIONS.values()
        }
        return {
            str(pattern.pattern).strip("/")
            for pattern in urlpatterns
            if isinstance(pattern, URLResolver)
            and str(pattern.pattern).strip("/") in registry_prefixes
        }
