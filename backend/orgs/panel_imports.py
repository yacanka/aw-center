"""Preview and confirm project-scoped panel workbook imports."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import re

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException

from .ata import normalize_ata_chapter
from .models import Panel
from .serializers import PanelSerializer


CONFIRMATION_SALT = "awcenter.organization-panel-import.v1"
HEADER_SCAN_ROWS = 10
FUZZY_MATCH_THRESHOLD = 0.84
IMPORT_FIELDS = ("panel", "ata")
FIELD_ALIASES = {
    "panel": (
        "panel",
        "panel name",
        "panel title",
        "certification panel",
        "panel adı",
        "panel ismi",
        "panel başlığı",
        "komite",
        "kurul",
    ),
    "ata": (
        "ata",
        "ata chapter",
        "ata chapter no",
        "ata chapter number",
        "ata no",
        "ata number",
        "chapter",
        "chapter no",
        "ata bölümü",
        "ata numarası",
    ),
}


class PanelImportVersionConflict(APIException):
    """Report that panel records changed after the reviewed preview."""

    status_code = 409
    default_code = "PANEL_IMPORT_VERSION_CONFLICT"
    default_detail = "Panel records changed after preview. Refresh and review the import again."


class PanelImportConfirmationRequired(APIException):
    """Require the signed preview before any panel import write."""

    status_code = 400
    default_code = "PANEL_IMPORT_CONFIRMATION_REQUIRED"
    default_detail = "Review the panel workbook before confirming the import."


class PanelImportPreviewExpired(APIException):
    """Reject an expired or malformed signed preview."""

    status_code = 400
    default_code = "PANEL_IMPORT_PREVIEW_EXPIRED"
    default_detail = "The panel import preview expired or is invalid."


class PanelImportPreviewMismatch(APIException):
    """Reject a workbook, user, or project that differs from preview."""

    status_code = 400
    default_code = "PANEL_IMPORT_PREVIEW_MISMATCH"
    default_detail = "The workbook does not match the reviewed panel import preview."


class PanelImportWorkbookInvalid(APIException):
    """Return a sanitized error when an Office package cannot be parsed."""

    status_code = 400
    default_code = "PANEL_IMPORT_WORKBOOK_INVALID"
    default_detail = "The panel workbook could not be read."


class PanelImportRowLimit(APIException):
    """Bound import work before validating or writing panel rows."""

    status_code = 400
    default_code = "PANEL_IMPORT_ROW_LIMIT"
    default_detail = "The panel workbook exceeds the configured row limit."


class PanelImportColumnsMissing(APIException):
    """Require both of the only supported panel import columns."""

    status_code = 400
    default_code = "PANEL_IMPORT_COLUMNS_MISSING"
    default_detail = "The panel workbook is missing required columns."


@dataclass(frozen=True, slots=True)
class HeaderMapping:
    row_index: int
    columns: dict[object, str]
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlannedPanel:
    row_number: int
    name: str
    ata: str
    target: Panel | None
    action: str


@dataclass(frozen=True, slots=True)
class PanelImportPlan:
    rows: tuple[PlannedPanel, ...]
    errors: tuple[dict, ...]
    mapping: dict

    @property
    def counts(self) -> dict[str, int]:
        counts = Counter(row.action for row in self.rows)
        return {
            "created_count": counts["create"],
            "updated_count": counts["update"],
            "unchanged_count": counts["unchanged"],
            "rejected_count": len(self.errors),
        }


def prepare_panel_import(uploaded_file, project, *, lock_existing=False) -> PanelImportPlan:
    """Read a workbook and produce a validated, non-mutating import plan."""

    import pandas as pd

    try:
        uploaded_file.seek(0)
        sample = pd.read_excel(uploaded_file, header=None, nrows=HEADER_SCAN_ROWS)
    except Exception as error:
        raise PanelImportWorkbookInvalid() from error

    header = _choose_header(sample)
    uploaded_file.seek(0)
    try:
        dataframe = pd.read_excel(uploaded_file, header=header.row_index)
    except Exception as error:
        raise PanelImportWorkbookInvalid() from error

    mapping = _mapping_preview(dataframe.columns, header)
    if header.missing:
        return PanelImportPlan((), (), mapping)

    dataframe = dataframe.rename(columns=header.columns)
    dataframe = dataframe.loc[:, [field for field in IMPORT_FIELDS if field in dataframe.columns]]
    dataframe = dataframe.astype(object).where(pd.notnull(dataframe), None)
    row_limit = max(int(settings.AWCENTER_MAX_PANEL_IMPORT_ROWS), 1)
    if len(dataframe) > row_limit:
        raise PanelImportRowLimit(
            f"Workbook has {len(dataframe)} rows; the limit is {row_limit}."
        )

    source_rows = tuple(
        (int(index) + header.row_index + 2, row.to_dict())
        for index, row in dataframe.iterrows()
    )
    return _build_plan(
        source_rows,
        project,
        mapping,
        lock_existing=lock_existing,
        entry_limit=row_limit,
    )


def create_panel_import_confirmation(uploaded_file, user, project, plan) -> str:
    """Bind a reviewed plan to its workbook, user, project, and database state."""

    return signing.dumps(
        {
            "version": 1,
            "sha256": _hash_upload(uploaded_file),
            "user_id": str(user.pk),
            "project": project.slug,
            "database_fingerprint": _plan_fingerprint(plan),
        },
        salt=CONFIRMATION_SALT,
        compress=True,
    )


def verify_panel_import_confirmation(token, uploaded_file, user, project) -> str:
    """Validate that confirmation still refers to the exact previewed source."""

    if not token:
        raise PanelImportConfirmationRequired()
    try:
        payload = signing.loads(
            token,
            salt=CONFIRMATION_SALT,
            max_age=max(int(settings.PANEL_IMPORT_PREVIEW_TTL_SECONDS), 1),
        )
    except (signing.BadSignature, signing.SignatureExpired) as error:
        raise PanelImportPreviewExpired() from error

    fingerprint = str(payload.get("database_fingerprint", ""))
    if not all(
        (
            payload.get("version") == 1,
            payload.get("sha256") == _hash_upload(uploaded_file),
            payload.get("user_id") == str(user.pk),
            payload.get("project") == project.slug,
            re.fullmatch(r"[0-9a-f]{64}", fingerprint),
        )
    ):
        raise PanelImportPreviewMismatch()
    return fingerprint


def execute_panel_import(uploaded_file, project, expected_fingerprint) -> PanelImportPlan:
    """Revalidate and atomically apply the exact plan approved in preview."""

    try:
        with transaction.atomic():
            plan = prepare_panel_import(uploaded_file, project, lock_existing=True)
            if _plan_fingerprint(plan) != expected_fingerprint:
                raise PanelImportVersionConflict()
            for row in plan.rows:
                if row.action == "unchanged":
                    continue
                serializer = PanelSerializer(
                    row.target,
                    data={"name": row.name, "ata": row.ata},
                    partial=row.target is not None,
                    context={"project": project},
                )
                serializer.is_valid(raise_exception=True)
                if row.target is None:
                    serializer.save(project=project)
                else:
                    serializer.save()
            return plan
    except IntegrityError as error:
        raise PanelImportVersionConflict() from error


def _choose_header(sample) -> HeaderMapping:
    best = HeaderMapping(0, {}, IMPORT_FIELDS)
    for row_index, row in sample.iterrows():
        mapping = _map_headers(row.tolist())
        missing = tuple(field for field in IMPORT_FIELDS if field not in mapping.values())
        candidate = HeaderMapping(int(row_index), mapping, missing)
        if len(candidate.missing) < len(best.missing):
            best = candidate
        if not candidate.missing:
            return candidate
    return best


def _map_headers(columns) -> dict[object, str]:
    aliases = {
        _normalize_header(alias): field
        for field, field_aliases in FIELD_ALIASES.items()
        for alias in field_aliases
    }
    mapping = {}
    used = set()
    for column in columns:
        normalized = _normalize_header(column)
        field = aliases.get(normalized) or _find_fuzzy_field(normalized, aliases)
        if field and field not in used:
            mapping[column] = field
            used.add(field)
    return mapping


def _normalize_header(value) -> str:
    text = "" if value is None else str(value)
    text = text.strip().casefold().replace("ı", "i")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _find_fuzzy_field(normalized, aliases) -> str | None:
    if not normalized:
        return None
    best_alias = max(
        aliases,
        key=lambda alias: SequenceMatcher(None, normalized, alias).ratio(),
    )
    score = SequenceMatcher(None, normalized, best_alias).ratio()
    return aliases[best_alias] if score >= FUZZY_MATCH_THRESHOLD else None


def _mapping_preview(columns, header: HeaderMapping) -> dict:
    return {
        "header_row": header.row_index + 1,
        "mapped_columns": [
            {"source": str(source), "target": target}
            for source, target in header.columns.items()
        ],
        "unmapped_columns": [
            str(column) for column in columns if column not in header.columns
        ],
        "missing_columns": list(header.missing),
    }


def _build_plan(source_rows, project, mapping, *, lock_existing, entry_limit):
    panels = Panel.objects.filter(project=project)
    if lock_existing:
        panels = panels.select_for_update()
    existing = {panel.ata: panel for panel in panels}
    candidates = []
    errors = []
    for row_number, source in source_rows:
        name_value = source.get("panel")
        ata_value = source.get("ata")
        if name_value in (None, "") and ata_value in (None, ""):
            continue
        name = re.sub(r"\s+", " ", str(name_value or "")).strip()
        if not name:
            errors.append(_row_error(row_number, "panel", "Panel name is required."))
            continue
        try:
            ata_values = _parse_ata_values(ata_value)
        except ValueError:
            errors.append(
                _row_error(
                    row_number,
                    "ata",
                    "Use an ATA chapter such as 27, 27-00, or 27-10.",
                )
            )
            continue
        for ata in ata_values:
            candidates.append((row_number, name, ata))

    if len(candidates) > entry_limit:
        raise PanelImportRowLimit(
            f"Workbook expands to more than {entry_limit} panel/ATA entries."
        )

    grouped = defaultdict(list)
    for candidate in candidates:
        grouped[candidate[2]].append(candidate)

    rows = []
    for ata, matches in grouped.items():
        names = {_canonical_name(name) for _row, name, _ata in matches}
        if len(names) > 1:
            for row_number in sorted({row for row, _name, _ata in matches}):
                errors.append(
                    _row_error(
                        row_number,
                        "ata",
                        f"ATA {ata} is assigned to more than one panel in the workbook.",
                    )
                )
            continue
        row_number, name, _ata = matches[0]
        target = existing.get(ata)
        serializer = PanelSerializer(
            target,
            data={"name": name, "ata": ata},
            partial=target is not None,
            context={"project": project},
        )
        if not serializer.is_valid():
            errors.append(
                {
                    "row": row_number,
                    "code": "PANEL_IMPORT_ROW_INVALID",
                    "fields": serializer.errors,
                }
            )
            continue
        action = "create" if target is None else "update" if target.name != name else "unchanged"
        rows.append(PlannedPanel(row_number, name, ata, target, action))

    rows.sort(key=lambda row: (row.row_number, row.ata))
    errors.sort(key=lambda error: (error["row"] is None, error["row"] or 0))
    return PanelImportPlan(tuple(rows), tuple(errors), mapping)


def _parse_ata_values(value) -> tuple[str, ...]:
    if value is None or value == "":
        raise ValueError
    if isinstance(value, str):
        text = str(value).strip()
        parts = re.split(r"(?:[;,\n|]+|\s+/\s+)", text)
    else:
        parts = [value]

    chapters = []
    for part in parts:
        chapter = normalize_ata_chapter(part)
        if chapter not in chapters:
            chapters.append(chapter)
    if not chapters:
        raise ValueError
    return tuple(chapters)


def _canonical_name(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _row_error(row, field, detail) -> dict:
    return {
        "row": row,
        "code": "PANEL_IMPORT_ROW_INVALID",
        "fields": {field: detail},
    }


def _hash_upload(uploaded_file) -> str:
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def _plan_fingerprint(plan) -> str:
    state = {
        "rows": [
            {
                "row": row.row_number,
                "name": row.name,
                "ata": row.ata,
                "action": row.action,
                "target": row.target.pk if row.target else None,
                "target_name": row.target.name if row.target else None,
                "target_discipline": row.target.discipline if row.target else None,
            }
            for row in plan.rows
        ],
        "errors": plan.errors,
        "mapping": plan.mapping,
    }
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
