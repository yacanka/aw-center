"""Read the supported DDF table layout without collapsing independent cells."""

from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from lxml.etree import XMLSyntaxError


class DDFImportError(Exception):
    """An unreadable Word package or unsupported DDF table structure."""


def read_ddf(uploaded_file):
    try:
        document = Document(uploaded_file)
        if document._element.body is None:
            raise DDFImportError()
        rows = [cell_texts(row) for table in document.tables for row in table.rows]
    except (BadZipFile, PackageNotFoundError, XMLSyntaxError, KeyError, ValueError) as error:
        raise DDFImportError() from error

    if len(rows) < 5 or any(len(rows[index]) < width for index, width in ((0, 2), (1, 2), (2, 6), (3, 2))):
        raise DDFImportError()
    # Metadata has label/value pairs; comments have at least number, authority,
    # and text. Do not assume label language or remove repeated field values.
    if any(not rows[row][column] for row, column in ((0, 0), (1, 0), (2, 0), (2, 2), (2, 4), (3, 0))):
        raise DDFImportError()
    if len(rows[4]) < 3 or any(len(row) < 3 for row in rows[5:]):
        raise DDFImportError()
    return {
        "project": rows[0][1],
        "doc_name": rows[1][1],
        "doc_no": rows[2][1],
        "doc_issue": rows[2][3],
        "date": rows[2][5],
        "commentor": rows[3][1],
        "comments": rows[5:],
    }


def cell_texts(row):
    # python-docx repeats the same XML cell for spanned grid positions. Only
    # those repeats are merged; equal text in distinct cells remains intact.
    seen, values = set(), []
    for cell in row.cells:
        if cell._tc not in seen:
            seen.add(cell._tc)
            values.append(cell.text.strip().replace("\n", " "))
    return values
