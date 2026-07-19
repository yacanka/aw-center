from io import BytesIO

import pandas as pd
from django.test import SimpleTestCase
from openpyxl import load_workbook

from .compdoc_excel_export import prepare_export_dataframe, write_workbook


class CompDocExcelExportTests(SimpleTestCase):
    """Verify safe export normalization and complete worksheet styling."""

    def test_export_merges_secondary_values_and_derives_status(self):
        """Internal fields are removed while workflow values remain readable."""

        dataframe = pd.DataFrame(
            [
                {
                    "id": "private-id",
                    "path": "/private/path",
                    "created_time": "2026-01-01",
                    "tech_doc_no": "TD-1",
                    "tech_doc_no_2": "TD-2",
                    "requirements": ["REQ-1", "REQ-2"],
                    "status_flow": [
                        {"status": "to_be_issued", "date": "01.01.2026"},
                        {"status": "authority_approved", "date": "02.01.2026"},
                    ],
                }
            ]
        )

        result = prepare_export_dataframe(dataframe)

        self.assertNotIn("Id", result.columns)
        self.assertNotIn("Path", result.columns)
        self.assertEqual(result.loc[0, "Tech Doc No"], "TD-1\nTD-2")
        self.assertEqual(result.loc[0, "Requirements"], "REQ-1\nREQ-2")
        self.assertEqual(result.loc[0, "Status"], "authority_approved")

    def test_row_striping_uses_last_column_not_last_row(self):
        """Conditional formatting spans every exported data column."""

        dataframe = pd.DataFrame([{"A": 1, "B": 2, "C": 3}, {"A": 4, "B": 5, "C": 6}])
        buffer = write_workbook(dataframe)
        worksheet = load_workbook(BytesIO(buffer.getvalue())).active
        formatting_ranges = [str(item.sqref) for item in worksheet.conditional_formatting]

        self.assertEqual(formatting_ranges, ["A2:C3"])
