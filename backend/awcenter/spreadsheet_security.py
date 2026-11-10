"""Bound spreadsheet reads and neutralize untrusted output values."""

from xml.etree.ElementTree import iterparse

from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

FORMULA_PREFIXES = frozenset("=+-@")


class SpreadsheetLimitError(ValueError):
    """A worksheet exceeds the caller's processing budget."""

    def __init__(self, detail, limit_kind):
        super().__init__(detail)
        self.limit_kind = limit_kind


def validate_worksheet_bounds(workbook, *, max_columns, max_rows=None,
                              max_characters=None, max_cells=None, header_rows=1):
    """Validate the first sheet before pandas allocates a rectangular frame.

    ``workbook`` is an open pandas ExcelFile. OOXML dimension hints cannot be
    trusted: pandas resets them, so actual cell coordinates must be checked.
    The helper never materializes worksheet rows and leaves resource ownership
    with the caller. Row limits include headers; cell limits exclude them.
    """

    if workbook.engine == "xlrd":
        sheet = workbook.book.sheet_by_index(0)
        _check_dimensions(sheet.nrows, sheet.ncols, max_rows, max_columns, max_cells, header_rows)
        return
    if workbook.engine != "openpyxl":
        raise ValueError("Unsupported spreadsheet reader.")
    sheet = workbook.book.worksheets[0]
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rows = current_row = current_column = last_row = width = characters = 0
    parents = []
    # openpyxl retains the resolved archive member on read-only worksheets.
    # Using that member also respects workbook relationship/sheet ordering.
    with workbook.book._archive.open(sheet._worksheet_path) as stream:
        for event, element in iterparse(stream, events=("start", "end")):
            if event == "start":
                parents.append(element)
            if event == "start" and element.tag == namespace + "row":
                rows += 1
                current_row = int(element.attrib.get("r", rows))
                current_column = 0
                last_row = max(last_row, rows, current_row)
                _check_dimensions(last_row, width, max_rows, max_columns, max_cells, header_rows)
            elif event == "start" and element.tag == namespace + "c":
                coordinate = element.attrib.get("r")
                if coordinate:
                    column, row = coordinate_from_string(coordinate)
                    current_column = column_index_from_string(column)
                    last_row = max(last_row, row)
                else:
                    current_column += 1
                width = max(width, current_column)
                _check_dimensions(last_row, width, max_rows, max_columns, max_cells, header_rows)
            elif event == "end" and element.tag == namespace + "t":
                characters += len(element.text or "")
                if max_characters is not None and characters > max_characters:
                    raise SpreadsheetLimitError("Worksheet text exceeds the processing limit.", "characters")
            if event == "end":
                element.clear()
                parents.pop()
                # clear() empties a node but leaves it attached to its parent;
                # detach it as well so completed rows cannot accumulate.
                if parents:
                    parents[-1].remove(element)


def _check_dimensions(rows, columns, max_rows, max_columns, max_cells, header_rows):
    if columns > max_columns:
        raise SpreadsheetLimitError("Worksheet columns exceed the processing limit.", "columns")
    if max_rows is not None and rows > max_rows:
        raise SpreadsheetLimitError("Worksheet rows exceed the processing limit.", "rows")
    if max_cells is not None and max(0, rows - header_rows) * columns > max_cells:
        raise SpreadsheetLimitError("Worksheet cells exceed the processing limit.", "cells")


def spreadsheet_safe_value(value):
    """Return text that spreadsheet applications cannot interpret as a formula."""

    if not isinstance(value, str):
        return value
    candidate = value.lstrip()
    if candidate and candidate[0] in FORMULA_PREFIXES:
        return f"'{value}"
    return value


def spreadsheet_safe_rows(rows):
    """Copy dictionary rows while neutralizing every untrusted string value."""

    return [
        {spreadsheet_safe_value(key): spreadsheet_safe_value(value) for key, value in row.items()}
        for row in rows
    ]


def spreadsheet_safe_dataframe(dataframe):
    """Copy a pandas-like DataFrame and neutralize its headings and cell values."""

    safe = dataframe.copy()
    safe.columns = [spreadsheet_safe_value(value) for value in safe.columns]
    return safe.map(spreadsheet_safe_value)
