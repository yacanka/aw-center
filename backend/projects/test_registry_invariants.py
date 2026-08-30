"""Architecture invariants for the canonical project catalog."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .constants import ALLOWED_PROJECT_CAPABILITIES
from .registry import PROJECT_DEFINITIONS


class ProjectRegistryInvariantTests(SimpleTestCase):
    def test_capabilities_are_known_and_dcc_metadata_is_complete(self):
        for slug, definition in PROJECT_DEFINITIONS.items():
            with self.subTest(slug=slug):
                self.assertFalse(set(definition.capabilities) - ALLOWED_PROJECT_CAPABILITIES)
                self.assertTrue(definition.dcc_template_name.endswith(".docx"))
                self.assertTrue(definition.mail_template_name)

    def test_no_per_project_runtime_package_exists(self):
        projects_root = Path(settings.BASE_DIR) / "projects"
        forbidden = [slug for slug in PROJECT_DEFINITIONS if (projects_root / slug).exists()]
        self.assertEqual(forbidden, [])
