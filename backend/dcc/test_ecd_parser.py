"""Contract tests for the PDF ECR parser used by Outlook Task."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from dcc.parsers import safe_ecd_parse


class EcdParserContractTests(SimpleTestCase):
    """Exercise pdfplumber against a representative table instead of a parser mock."""

    def test_parser_reads_expected_outlook_task_fields_from_pdf(self):
        """A table-based ECR PDF yields the fields consumed by JIRA creation."""

        upload = SimpleUploadedFile("change.pdf", ecr_pdf(), content_type="application/pdf")

        parsed = safe_ecd_parse(upload)

        self.assertEqual(parsed["ecd_no"], "ECD-42 / REV")
        self.assertEqual(parsed["ecd_title"], "Validated change")
        self.assertEqual(parsed["requestor"], "Requestor")
        self.assertEqual(parsed["ata"], "27")
        self.assertEqual(parsed["subata"], "10")


def ecr_pdf():
    """Build a dependency-free one-page PDF containing the legacy ECR table shape."""

    cells = {
        (2, 0): "Validated change",
        (4, 0): "ECD-42 / REV-A-extra",
        (4, 1): "AW Center",
        (4, 2): "Minor",
        (4, 3): "Design",
        (7, 0): "Initial",
        (9, 1): "Aircraft 1",
        (11, 1): "Requestor",
        (13, 1): "Originator",
        (14, 1): "27/10",
        (15, 1): "Justification",
        (16, 1): "Solution",
        (17, 1): "Consequence",
        (18, 1): "Systems",
    }
    return pdf_document(table_commands(cells))


def table_commands(cells):
    """Return PDF drawing commands for a nineteen-row, four-column table."""

    columns, top, row_height = [30, 180, 310, 440, 570], 740, 35
    commands = ["0.5 w"]
    commands.extend(f"{x} 75 m {x} {top} l S" for x in columns)
    commands.extend(f"30 {top - row * row_height} m 570 {top - row * row_height} l S" for row in range(20))
    for (row, column), value in cells.items():
        x, y = columns[column] + 3, top - (row + 1) * row_height + 12
        commands.append(f"BT /F1 8 Tf {x} {y} Td ({escape_pdf(value)}) Tj ET")
    return "\n".join(commands).encode()


def pdf_document(stream):
    """Wrap a content stream in a minimal valid PDF object graph."""

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    body, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body.extend(b"%d 0 obj\n%s\nendobj\n" % (index, obj))
    return finish_pdf(body, offsets)


def finish_pdf(body, offsets):
    """Append a classic xref table and trailer to a PDF byte buffer."""

    xref = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    body.extend("".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]).encode())
    body.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(body)


def escape_pdf(value):
    """Escape literal-string delimiters in generated PDF test text."""

    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
