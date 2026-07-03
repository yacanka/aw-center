from unittest import TestCase

from common.compdoc_import import HeaderMappingResult, build_mapping_preview, choose_header_row, map_headers


MODEL_FIELDS = {
    "name",
    "panel",
    "responsible",
    "status",
    "cat",
    "moc",
    "cover_page_no",
    "cover_page_issue",
    "tech_doc_no",
    "tech_doc_issue",
}


class FakeExcelFile:
    """Minimal seek-compatible Excel file double for header selection tests."""

    def seek(self, position):
        """Accept seek calls made between header-row probes."""


class FakeDataFrame:
    """Minimal dataframe double exposing only columns."""

    def __init__(self, columns):
        """Store fake dataframe columns."""

        self.columns = columns


class FakePandas:
    """Minimal pandas double that returns per-header fake dataframes."""

    columns_by_header = {
        0: ["Exported by AW Center", None, None],
        1: [
            "Document Name",
            "Panel",
            "Owner",
            "State",
            "LOI",
            "Means of Compliance",
            "Cover Page Number",
            "Cover Page Issue",
            "Technical Document No",
            "Technical Document Issue",
        ],
    }

    @classmethod
    def read_excel(cls, excel_file, header=0):
        """Return a fake dataframe for the requested header row."""

        return FakeDataFrame(cls.columns_by_header[header])


class ComplianceDocumentImportMappingTests(TestCase):
    def test_maps_static_multilingual_aliases_to_model_fields(self):
        mapping = map_headers(["İsim", "Document Name", "MOC", "Tech Document Number"], MODEL_FIELDS)

        self.assertEqual(mapping["İsim"], "name")
        self.assertEqual(mapping["MOC"], "moc")
        self.assertEqual(mapping["Tech Document Number"], "tech_doc_no")

    def test_maps_fuzzy_header_typo_when_similarity_is_confident(self):
        mapping = map_headers(["Documnt Name", "Cover Page Numbr"], MODEL_FIELDS)

        self.assertEqual(mapping["Documnt Name"], "name")
        self.assertEqual(mapping["Cover Page Numbr"], "cover_page_no")

    def test_selects_second_row_when_it_contains_import_headers(self):
        header_result = choose_header_row(FakeExcelFile(), FakePandas, MODEL_FIELDS)

        self.assertEqual(header_result.header_row_index, 1)
        self.assertFalse(header_result.missing_fields)

    def test_builds_preview_with_mapped_and_unmapped_columns(self):
        header_result = choose_header_row(FakeExcelFile(), FakePandas, MODEL_FIELDS)
        preview = build_mapping_preview(FakePandas.columns_by_header[1] + ["Ignored"], header_result)

        self.assertEqual(preview["header_row"], 2)
        self.assertIn({"source": "Document Name", "target": "name"}, preview["mapped_columns"])
        self.assertEqual(preview["unmapped_columns"], ["Ignored"])

    def test_preview_includes_missing_columns_for_incomplete_mapping(self):
        header_result = HeaderMappingResult(0, {"Document Name": "name"}, ["panel"])
        preview = build_mapping_preview(["Document Name", "Unknown"], header_result)

        self.assertEqual(preview["missing_columns"], ["panel"])
