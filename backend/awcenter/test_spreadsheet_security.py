from io import BytesIO
import tracemalloc
from zipfile import ZIP_DEFLATED, ZipFile

from django.test import SimpleTestCase
from openpyxl import load_workbook
import pandas as pd

from awcenter.spreadsheet_security import (
    SpreadsheetLimitError,
    spreadsheet_safe_dataframe,
    spreadsheet_safe_value,
    validate_worksheet_bounds,
)


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


class WorksheetScannerTests(SimpleTestCase):
    def worksheet_package(self, rows):
        original = BytesIO()
        with pd.ExcelWriter(original, engine="openpyxl") as writer:
            pd.DataFrame({"value": ["Example"]}).to_excel(writer, index=False)
        xml = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<dimension ref="A1:A1"/><sheetData>' + rows + '</sheetData></worksheet>').encode()
        output = BytesIO()
        with ZipFile(original) as source, ZipFile(output, "w", ZIP_DEFLATED) as destination:
            for entry in source.infolist():
                destination.writestr(entry, xml if entry.filename == "xl/worksheets/sheet1.xml" else source.read(entry.filename))
        output.seek(0)
        return output

    def scanner_peak(self, count):
        rows = "".join(f'<row r="{index}"/>' for index in range(1, count + 1))
        with pd.ExcelFile(self.worksheet_package(rows)) as workbook:
            tracemalloc.start()
            try:
                validate_worksheet_bounds(workbook, max_columns=100)
                return tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()

    def test_completed_rows_do_not_accumulate_in_streaming_scanner(self):
        # Both samples exceed XML/decompressor chunk sizes, so this compares
        # retained rows rather than startup buffer growth for a tiny document.
        small_peak = self.scanner_peak(5000)
        large_peak = self.scanner_peak(20000)
        # XML parser chunk buffers may vary, but keeping every cleared row
        # attached to sheetData grows by over a megabyte for this input.
        self.assertLess(large_peak - small_peak, 256 * 1024)

    def test_streaming_scanner_keeps_dimension_and_text_guards(self):
        rows = '<row r="3"><c r="B3" t="inlineStr"><is><t>Example</t></is></c></row>'
        for bounds, kind in (({"max_columns": 1}, "columns"), ({"max_columns": 2, "max_rows": 2}, "rows"),
                             ({"max_columns": 2, "max_characters": 4}, "characters"),
                             ({"max_columns": 2, "max_cells": 1}, "cells")):
            with self.subTest(bounds=bounds), pd.ExcelFile(self.worksheet_package(rows)) as workbook:
                with self.assertRaises(SpreadsheetLimitError) as rejected:
                    validate_worksheet_bounds(workbook, **bounds)
                self.assertEqual(rejected.exception.limit_kind, kind)
