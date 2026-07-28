from django.test import SimpleTestCase

from common.compdoc_fields import get_compdoc_field_metadata
from projects.ozgur.models import CompDoc
from projects.aesa.models import CompDoc as AesaCompDoc
from projects.blok4050.models import CompDoc as Blok4050CompDoc
from projects.gokbey.models import CompDoc as GokbeyCompDoc


class ComplianceDocumentFieldMetadataTests(SimpleTestCase):
    def test_returns_frontend_safe_model_field_metadata(self):
        fields = get_compdoc_field_metadata(CompDoc)
        field_by_key = {field["key"]: field for field in fields}

        self.assertIn("name", field_by_key)
        self.assertEqual(field_by_key["name"]["label"], "Name")
        self.assertEqual(field_by_key["name"]["filter_kind"], "text")
        self.assertTrue(field_by_key["name"]["sortable"])
        self.assertTrue(field_by_key["name"]["default_visible"])

    def test_workflow_projection_is_queryable_but_source_json_is_not_exposed(self):
        fields = get_compdoc_field_metadata(CompDoc)
        field_by_key = {field["key"]: field for field in fields}

        self.assertEqual(field_by_key["status"]["filter_kind"], "select")
        self.assertEqual(field_by_key["ubm_target_date"]["filter_kind"], "date")
        self.assertNotIn("status_flow", field_by_key)

    def test_exposes_only_documented_metadata_keys(self):
        fields = get_compdoc_field_metadata(CompDoc)
        metadata_keys = set(fields[0].keys())

        self.assertEqual(
            metadata_keys,
            {
                "key",
                "label",
                "type",
                "width",
                "filter_kind",
                "sortable",
                "default_visible",
                "ellipsis",
                "choices",
                "option_source",
            },
        )

    def test_secondary_document_fields_are_server_discoverable(self):
        for model in (AesaCompDoc, GokbeyCompDoc, Blok4050CompDoc):
            with self.subTest(project=model._meta.app_label):
                keys = {field["key"] for field in get_compdoc_field_metadata(model)}
                self.assertIn("tech_doc_no_2", keys)
                self.assertIn("tech_doc_issue_2", keys)
                self.assertIn("delivered_tech_doc_issue_2", keys)
