"""Tests for the technical project capability catalog."""

from types import MappingProxyType
from unittest import TestCase

from .registry import (
    GOKBEY_DCC_CONTROLLER,
    PROJECT_DEFINITIONS,
    UnknownProjectDefinitionError,
    find_project_by_jira_component,
    get_project_definition,
    get_project_definitions_by_capability,
)


class ProjectRegistryTests(TestCase):
    def test_catalog_contains_exact_first_production_projects(self):
        self.assertEqual(
            set(PROJECT_DEFINITIONS),
            {"ozgur", "piku", "aesa", "havasoj", "hys", "blok30", "blok4050", "gokbey"},
        )
        self.assertIsInstance(PROJECT_DEFINITIONS, MappingProxyType)

    def test_catalog_exposes_only_technical_metadata(self):
        forbidden = {"display_name", "enabled", "app_label", "url_prefix", "tags"}
        for definition in PROJECT_DEFINITIONS.values():
            self.assertTrue(definition.capabilities)
            self.assertTrue(definition.jira_component)
            self.assertTrue(forbidden.isdisjoint(vars(definition)))

    def test_lookup_and_capability_filter_are_explicit(self):
        self.assertEqual(get_project_definition(" OZGUR ").slug, "ozgur")
        with self.assertRaises(UnknownProjectDefinitionError):
            get_project_definition("unknown")
        self.assertEqual(
            {item.slug for item in get_project_definitions_by_capability(" DCC ")},
            set(PROJECT_DEFINITIONS),
        )
        self.assertEqual(find_project_by_jira_component(" aesa ").slug, "aesa")
        self.assertIsNone(find_project_by_jira_component("unknown"))
        self.assertEqual(
            PROJECT_DEFINITIONS["gokbey"].dcc_controller,
            GOKBEY_DCC_CONTROLLER,
        )
