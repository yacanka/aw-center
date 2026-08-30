"""Bounded PDF parser for the canonical ECR review workflow."""

from collections.abc import Callable
import unicodedata

import pdfplumber

MAX_PAGES = 3
MAX_TABLE_ROWS = 100
MAX_TABLE_COLUMNS = 30
MAX_CELL_CHARACTERS = 5000
MAX_DOCUMENT_CHARACTERS = 50000

SNAPSHOT_KEYS = (
    "ecr_number",
    "title",
    "project",
    "change_class",
    "change_type",
    "effectivity",
    "track_type",
    "record_of_change",
    "requestor",
    "originator",
    "ata",
    "subata",
    "initiator",
    "justification",
    "proposed_solution",
    "nonimplementation_consequence",
    "impacted_groups",
)


class EcrPdfParseError(ValueError):
    """Represent an unreadable or unsupported ECR document."""


def parse_ecr_pdf(upload) -> dict[str, str]:
    """Return an immutable, whitespace-normalized ECR snapshot."""

    try:
        upload.seek(0)
        with pdfplumber.open(upload) as pdf:
            if not 1 <= len(pdf.pages) <= MAX_PAGES:
                raise EcrPdfParseError("The ECR PDF has an unsupported page count.")
            tables = extract_candidate_tables(pdf.pages)
    except EcrPdfParseError:
        raise
    except Exception as error:
        raise EcrPdfParseError("The ECR PDF could not be read.") from error
    finally:
        upload.seek(0)

    parsers: tuple[Callable[[list[list[str]]], dict[str, str]], ...] = (
        parse_table_layout_one,
        parse_table_layout_two,
    )
    for table in tables:
        for parser in parsers:
            try:
                snapshot = complete_snapshot(parser(table))
                validate_required_snapshot(snapshot)
                return snapshot
            except (EcrPdfParseError, IndexError, TypeError, ValueError):
                continue
    raise EcrPdfParseError("The PDF does not contain a supported ECR table.")


def extract_candidate_tables(pages) -> list[list[list[str]]]:
    """Extract only bounded tables before applying known ECR layouts."""

    tables = []
    total_characters = 0
    for page in pages:
        for raw_table in page.extract_tables() or ():
            if not raw_table or len(raw_table) > MAX_TABLE_ROWS:
                continue
            table = []
            for raw_row in raw_table:
                if len(raw_row or ()) > MAX_TABLE_COLUMNS:
                    raise EcrPdfParseError("The ECR table is too wide.")
                row = [normalize_cell(value) for value in raw_row or ()]
                total_characters += sum(len(value) for value in row)
                if total_characters > MAX_DOCUMENT_CHARACTERS:
                    raise EcrPdfParseError("The ECR table contains too much text.")
                table.append(row)
            tables.append(table)
    return tables


def normalize_cell(value) -> str:
    """Collapse control whitespace and cap one untrusted PDF cell."""

    printable = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in str(value or "")
    )
    text = " ".join(printable.split())
    if len(text) > MAX_CELL_CHARACTERS:
        raise EcrPdfParseError("An ECR table cell contains too much text.")
    return text


def parse_table_layout_one(table) -> dict[str, str]:
    """Parse the current nineteen-row ECR table layout."""

    ata, subata = split_ata(cell(table, 14, 1))
    number = "-".join(cell(table, 4, 0).split("-")[:2]).strip()
    return {
        "ecr_number": number,
        "title": cell(table, 2, 0),
        "project": cell(table, 4, 1),
        "change_class": cell(table, 4, 2),
        "change_type": cell(table, 4, 3),
        "effectivity": cell(table, 9, 1),
        "track_type": cell(table, 10, 1),
        "record_of_change": cell(table, 7, 0),
        "requestor": cell(table, 11, 1),
        "originator": cell(table, 13, 1),
        "ata": ata,
        "subata": subata,
        "justification": cell(table, 15, 1),
        "proposed_solution": cell(table, 16, 1),
        "nonimplementation_consequence": cell(table, 17, 1),
        "impacted_groups": cell(table, 18, 1).replace("\n", ", "),
    }


def parse_table_layout_two(table) -> dict[str, str]:
    """Parse the alternate layout with one extra originator row."""

    title = cell(table, 2, 0)
    raw_number = cell(table, 4, 0)
    number = raw_number.split(title, 1)[0].rstrip(" -") if title in raw_number else raw_number
    ata, subata = split_ata(cell(table, 15, 1))
    return {
        "ecr_number": number,
        "title": title,
        "project": cell(table, 4, 1),
        "change_class": cell(table, 4, 2),
        "change_type": cell(table, 4, 3),
        "effectivity": cell(table, 9, 1),
        "track_type": cell(table, 10, 1),
        "record_of_change": cell(table, 7, 0),
        "requestor": cell(table, 12, 1),
        "originator": cell(table, 14, 1),
        "ata": ata,
        "subata": subata,
        "justification": cell(table, 16, 1),
        "proposed_solution": cell(table, 17, 1),
        "nonimplementation_consequence": cell(table, 18, 1),
        "impacted_groups": cell(table, 19, 1).replace("\n", ", "),
    }


def cell(table, row, column) -> str:
    """Read one required layout coordinate."""

    return table[row][column]


def split_ata(value) -> tuple[str, str]:
    """Split an ATA/sub-ATA pair without inventing missing values."""

    if "/" not in value:
        return "", ""
    ata, subata = value.split("/", 1)
    return ata.strip(), subata.strip()


def complete_snapshot(values) -> dict[str, str]:
    """Guarantee the stable public snapshot shape."""

    return {key: normalize_cell(values.get(key, "")) for key in SNAPSHOT_KEYS}


def validate_required_snapshot(snapshot) -> None:
    """Reject false-positive tables that lack the ECR identity."""

    if not snapshot["ecr_number"] or not snapshot["title"]:
        raise EcrPdfParseError("The ECR number and title are required.")
