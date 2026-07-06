from django.test import SimpleTestCase

from common.compdoc_fields import get_compdoc_field_metadata
from projects.ozgur.models import CompDoc


class ComplianceDocumentFieldMetadataTests(SimpleTestCase):
    def test_returns_frontend_safe_model_field_metadata(self):
        fields = get_compdoc_field_metadata(CompDoc)
        field_by_key = {field["key"]: field for field in fields}

        self.assertIn("name", field_by_key)
        self.assertEqual(field_by_key["name"]["label"], "Name")
        self.assertTrue(field_by_key["name"]["filter"])
        self.assertTrue(field_by_key["name"]["sorter"])

    def test_exposes_only_documented_metadata_keys(self):
        fields = get_compdoc_field_metadata(CompDoc)
        metadata_keys = set(fields[0].keys())

        self.assertEqual(
            metadata_keys,
            {"key", "label", "type", "width", "filter", "sorter", "ellipsis"},
        )
