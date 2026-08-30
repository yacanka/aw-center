from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import load_workbook
import pandas as pd

from awcenter.spreadsheet_security import spreadsheet_safe_dataframe, spreadsheet_safe_value


class SpreadsheetSecurityTests(SimpleTestCase):
    def test_formula_prefixes_are_written_as_text(self):
        dataframe = pd.DataFrame(
            [{"value": "=1+1"}, {"value": "  @SUM(A1:A2)"}, {"value": "ordinary"}]
        )
        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            spreadsheet_safe_dataframe(dataframe).to_excel(writer, index=False)

        worksheet = load_workbook(BytesIO(output.getvalue()), data_only=False).active
        self.assertEqual(worksheet["A2"].data_type, "s")
        self.assertEqual(worksheet["A3"].data_type, "s")
        self.assertEqual(worksheet["A4"].value, "ordinary")

    def test_non_text_values_are_not_changed(self):
        self.assertEqual(spreadsheet_safe_value(-5), -5)
        self.assertIsNone(spreadsheet_safe_value(None))
