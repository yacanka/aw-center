"""Helpers for tolerant compliance-document Excel imports."""

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

REQUIRED_IMPORT_FIELDS = (
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
)

LIST_IMPORT_FIELDS = ("signature_panel", "requirements", "status_flow")
HEADER_SCAN_ROWS = 2
FUZZY_MATCH_THRESHOLD = 0.84

FIELD_ALIASES = {
    "name": ("name", "document name", "doc name", "document title", "title", "isim", "ad"),
    "panel": ("panel", "discipline", "komite", "kurul"),
    "signature_panel": ("signature panel", "sign panel", "approval panel", "imza paneli"),
    "ata": ("ata", "ata chapter", "chapter", "ata no"),
    "responsible": ("responsible", "owner", "assignee", "person in charge", "sorumlu"),
    "status": ("status", "state", "document status", "durum"),
    "cat": ("cat", "category", "loi", "classification", "kategori"),
    "moc": ("moc", "means of compliance", "compliance method"),
    "mom_no": ("mom no", "mom number", "meeting minutes no", "minutes no"),
    "cover_page_no": ("cover page no", "cover page number", "cover no", "cp no"),
    "cover_page_issue": ("cover page issue", "cover issue", "cp issue"),
    "tech_doc_no": ("tech doc no", "technical document no", "tech document number", "td no"),
    "tech_doc_issue": ("tech doc issue", "technical document issue", "td issue"),
    "delivered_tech_doc_issue": ("delivered tech doc issue", "delivered issue", "delivery issue"),
    "ubm_target_date": ("ubm target date", "target date", "planned date", "hedef tarih"),
    "ubm_delivery_date": ("ubm delivery date", "delivery date", "delivered date", "teslim tarih"),
    "requirements": ("requirements", "requirement", "reqs", "gereksinimler"),
    "status_flow": ("status flow", "workflow", "status history", "flow"),
    "notes": ("notes", "note", "comments", "remarks", "açıklama", "not"),
    "path": ("path", "file path", "document path", "location"),
}


@dataclass(frozen=True)
class HeaderMappingResult:
    """Describe the selected Excel header row and model-field column mapping."""

    header_row_index: int
    column_mapping: dict[str, str]
    missing_fields: list[str]


def normalize_header(value) -> str:
    """Normalize a model or spreadsheet header for deterministic matching."""

    text = "" if value is None else str(value)
    text = text.strip().casefold().replace("ı", "i")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def model_field_to_header(field_name: str) -> str:
    """Convert a serializer/model field name into a normalized header label."""

    return normalize_header(field_name.replace("_", " "))


def build_alias_lookup(model_fields: set[str]) -> dict[str, str]:
    """Create a normalized alias-to-model-field lookup for importable fields."""

    lookup = {model_field_to_header(field): field for field in model_fields}
    for field, aliases in FIELD_ALIASES.items():
        if field not in model_fields:
            continue
        lookup.update({normalize_header(alias): field for alias in aliases})
    return lookup


def resolve_header_field(header, alias_lookup: dict[str, str]) -> str | None:
    """Resolve a spreadsheet header to a model field using aliases and fuzzy text."""

    normalized_header = normalize_header(header)
    if not normalized_header:
        return None
    if normalized_header in alias_lookup:
        return alias_lookup[normalized_header]
    return find_fuzzy_field(normalized_header, alias_lookup)


def find_fuzzy_field(normalized_header: str, alias_lookup: dict[str, str]) -> str | None:
    """Return the closest field when the header is confidently similar."""

    best_alias = ""
    best_score = 0.0
    for alias in alias_lookup:
        score = SequenceMatcher(None, normalized_header, alias).ratio()
        if score > best_score:
            best_alias, best_score = alias, score
    if best_score < FUZZY_MATCH_THRESHOLD:
        return None
    return alias_lookup[best_alias]


def map_headers(columns, model_fields: set[str]) -> dict[str, str]:
    """Map dataframe columns to serializer/model fields without duplicates."""

    mapping = {}
    used_fields = set()
    alias_lookup = build_alias_lookup(model_fields)
    for column in columns:
        field = resolve_header_field(column, alias_lookup)
        if field and field not in used_fields:
            mapping[column] = field
            used_fields.add(field)
    return mapping


def choose_header_row(excel_file, pandas_module, model_fields: set[str]) -> HeaderMappingResult:
    """Choose the best header row from the first supported Excel rows."""

    best_result = None
    for header_index in range(HEADER_SCAN_ROWS):
        dataframe = try_read_excel_header(excel_file, pandas_module, header_index)
        if dataframe is None:
            continue
        mapping = map_headers(dataframe.columns, model_fields)
        missing = get_missing_required_fields(mapping.values(), model_fields)
        result = HeaderMappingResult(header_index, mapping, missing)
        if best_result is None or len(result.missing_fields) < len(best_result.missing_fields):
            best_result = result
        excel_file.seek(0)
    return best_result or HeaderMappingResult(0, {}, list(REQUIRED_IMPORT_FIELDS))


def try_read_excel_header(excel_file, pandas_module, header_index: int):
    """Read one candidate Excel header row and tolerate missing rows."""

    try:
        return pandas_module.read_excel(excel_file, header=header_index)
    except ValueError:
        excel_file.seek(0)
        return None


def get_missing_required_fields(mapped_fields, model_fields: set[str]) -> list[str]:
    """Return required import fields that were not mapped from the spreadsheet."""

    required_fields = [field for field in REQUIRED_IMPORT_FIELDS if field in model_fields]
    mapped_field_set = set(mapped_fields)
    return [field for field in required_fields if field not in mapped_field_set]


def get_unmapped_columns(columns, column_mapping: dict[str, str]) -> list[str]:
    """Return spreadsheet columns that were not matched to model fields."""

    return [str(column) for column in columns if column not in column_mapping]


def build_mapping_preview(columns, header_result: HeaderMappingResult) -> dict:
    """Build a frontend-safe import mapping preview payload."""

    mapped_columns = [
        {"source": str(source), "target": target}
        for source, target in header_result.column_mapping.items()
    ]
    return {
        "header_row": header_result.header_row_index + 1,
        "mapped_columns": mapped_columns,
        "unmapped_columns": get_unmapped_columns(columns, header_result.column_mapping),
        "missing_columns": header_result.missing_fields,
    }


def read_mapped_excel(excel_file, pandas_module, header_result: HeaderMappingResult):
    """Read Excel data using the selected header row and normalized field names."""

    dataframe = pandas_module.read_excel(excel_file, header=header_result.header_row_index)
    dataframe = dataframe.rename(columns=header_result.column_mapping)
    return dataframe.loc[:, [column for column in dataframe.columns if column in header_result.column_mapping.values()]]
