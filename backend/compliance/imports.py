"""Preview/confirm workbook imports bound to document UUID and version."""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from orgs.models import Panel

from .compdoc_import import build_mapping_preview, choose_header_row, read_mapped_excel
from .compdoc_workflow import WORKFLOW_STATUSES, parse_workflow_date
from .models import ComplianceDocument, CoverPage, ImportAudit, WorkflowEvent
from .serializers import ComplianceDocumentSerializer
from .services import VersionConflict, transition_document, update_document


CONFIRMATION_SALT = "awcenter.compliance-import.v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IMPORT_FIELDS = {
    "id",
    "name",
    "panel",
    "signature_panel",
    "responsible",
    "cat",
    "moc",
    "mom_no",
    "cover_page_no",
    "cover_page_issue",
    "tech_doc_no",
    "tech_doc_issue",
    "delivered_tech_doc_issue",
    "tech_doc_no_2",
    "tech_doc_issue_2",
    "delivered_tech_doc_issue_2",
    "requirements",
    "status",
    "effective_date",
    "ubm_target_date",
    "ubm_delivery_date",
    "notes",
    "path",
}
MODEL_FIELDS = {
    "name",
    "signature_panel",
    "responsible",
    "cat",
    "moc",
    "mom_no",
    "tech_doc_no",
    "tech_doc_issue",
    "delivered_tech_doc_issue",
    "tech_doc_no_2",
    "tech_doc_issue_2",
    "delivered_tech_doc_issue_2",
    "requirements",
    "notes",
    "path",
}
LIST_FIELDS = {"signature_panel", "requirements"}


@dataclass(frozen=True, slots=True)
class PlannedWorkflowEvent:
    status: str
    effective_date: date


@dataclass(frozen=True, slots=True)
class PlannedRow:
    row_number: int
    payload: dict
    workflow_events: tuple[PlannedWorkflowEvent, ...]
    target: ComplianceDocument | None
    action: str


@dataclass(frozen=True, slots=True)
class ImportPlan:
    rows: tuple[PlannedRow, ...]
    errors: tuple[dict, ...]
    mapping: dict

    @property
    def counts(self):
        counts = Counter(row.action for row in self.rows)
        return {
            "created_count": counts["create"],
            "updated_count": counts["update"],
            "unchanged_count": counts["unchanged"],
            "rejected_count": len(self.errors),
        }


def hash_upload(uploaded_file) -> str:
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def prepare_plan(uploaded_file, project, request, *, lock_existing=False) -> ImportPlan:
    import pandas as pd

    header = choose_header_row(uploaded_file, pd, IMPORT_FIELDS)
    uploaded_file.seek(0)
    preview_frame = pd.read_excel(uploaded_file, header=header.header_row_index)
    mapping = build_mapping_preview(preview_frame.columns, header)
    if mapping["missing_columns"]:
        return ImportPlan((), ({
            "row": None,
            "code": "IMPORT_COLUMNS_MISSING",
            "fields": {"columns": mapping["missing_columns"]},
        },), mapping)
    uploaded_file.seek(0)
    dataframe = read_mapped_excel(uploaded_file, pd, header)
    dataframe = dataframe.astype(object).where(pd.notnull(dataframe), None)
    row_limit = max(int(settings.AWCENTER_MAX_COMPDOC_IMPORT_ROWS), 1)
    if len(dataframe) > row_limit:
        raise ValidationError(
            {"file": f"Workbook has {len(dataframe)} rows; the limit is {row_limit}."},
            code="IMPORT_ROW_LIMIT",
        )

    source_rows = tuple(
        (
            int(index) + header.header_row_index + 2,
            source.to_dict(),
        )
        for index, source in dataframe.iterrows()
    )
    return prepare_tabular_plan(
        source_rows,
        project,
        request,
        mapping=mapping,
        lock_existing=lock_existing,
    )


def prepare_tabular_plan(
    source_rows,
    project,
    request,
    *,
    mapping,
    lock_existing=False,
) -> ImportPlan:
    """Apply the canonical Excel validation and matching rules to mapped rows."""

    documents = (
        ComplianceDocument.objects.filter(project=project)
        .select_related("cover_page", "panel")
        .prefetch_related(
            Prefetch(
                "workflow_events",
                queryset=WorkflowEvent.objects.order_by("sequence"),
                to_attr="import_workflow_events",
            )
        )
    )
    if lock_existing:
        # ``panel`` is nullable, so PostgreSQL renders its select_related join as
        # an outer join and rejects an unscoped FOR UPDATE.  Only document rows
        # participate in the optimistic import contract; related objects remain
        # eager-loaded without broadening the lock surface.
        documents = documents.select_for_update(of=("self",))
    existing_documents = list(documents)
    cover_pages = CoverPage.objects.filter(project=project)
    if lock_existing:
        cover_pages = cover_pages.select_for_update()
    cover_pages_by_number = {
        _canonical_identity(cover_page.number): cover_page
        for cover_page in cover_pages
    }
    by_id = {str(document.pk): document for document in existing_documents}
    by_key = {}
    ambiguous_keys = set()
    for document in existing_documents:
        for key in _document_keys(document):
            if key in by_key and by_key[key].pk != document.pk:
                ambiguous_keys.add(key)
                continue
            by_key[key] = document
    panels = list(Panel.objects.filter(project=project))
    panel_lookup = {
        key.casefold(): panel
        for panel in panels
        for key in (panel.ata, panel.name)
        if key
    }

    normalized = []
    errors = []
    for row_number, source in source_rows:
        try:
            normalized.append((row_number, _normalize_row(source, panel_lookup)))
        except ValidationError as error:
            errors.append(_row_error(row_number, error))

    identity_counts = Counter(
        key
        for _, normalized_row in normalized
        for key in _payload_keys(normalized_row)
    )
    duplicates = {key for key, count in identity_counts.items() if count > 1}
    planned = []
    for row_number, normalized_row in normalized:
        payload = normalized_row["payload"]
        target = None
        document_id = normalized_row["id"]
        if document_id:
            target = by_id.get(document_id)
            if target is None:
                errors.append(
                    {
                        "row": row_number,
                        "code": "IMPORT_DOCUMENT_NOT_FOUND",
                        "fields": {"id": "Document UUID does not exist in this project."},
                    }
                )
                continue
        else:
            keys = _payload_keys(normalized_row)
            if any(key in duplicates for key in keys):
                errors.append(
                    {
                        "row": row_number,
                        "code": "IMPORT_DUPLICATE_IDENTITY",
                        "fields": {"document": "Workbook contains this identity more than once."},
                    }
                )
                continue
            if any(key in ambiguous_keys for key in keys):
                errors.append(
                    {
                        "row": row_number,
                        "code": "IMPORT_IDENTITY_CONFLICT",
                        "fields": {
                            "document": (
                                "More than one existing document matches this identity; "
                                "export and provide the document UUID."
                            )
                        },
                    }
                )
                continue
            matches = {by_key[key] for key in keys if key in by_key}
            if len(matches) > 1:
                errors.append(
                    {
                        "row": row_number,
                        "code": "IMPORT_IDENTITY_CONFLICT",
                        "fields": {
                            "document": (
                                "The document name and technical number match different existing "
                                "documents; export and provide the document UUID."
                            )
                        },
                    }
                )
                continue
            target = next(iter(matches), None)
        if target is not None and target.is_archived:
            errors.append(
                {
                    "row": row_number,
                    "code": "IMPORT_TARGET_ARCHIVED",
                    "fields": {"document": "Archived documents must be restored before import."},
                }
            )
            continue

        cover_page = cover_pages_by_number.get(
            _canonical_identity(payload["cover_page"]["number"])
        )
        if cover_page is not None:
            payload["cover_page"]["version"] = cover_page.version

        serializer = ComplianceDocumentSerializer(
            target,
            data=payload,
            partial=target is not None,
            context={"request": request, "project": project},
        )
        if not serializer.is_valid():
            errors.append(
                {
                    "row": row_number,
                    "code": "IMPORT_ROW_INVALID",
                    "fields": serializer.errors,
                }
            )
            continue
        try:
            workflow_events = _pending_workflow_events(target, normalized_row)
        except ValidationError as error:
            errors.append(_row_error(row_number, error))
            continue
        action = _resolve_action(target, serializer.validated_data, workflow_events)
        planned.append(
            PlannedRow(
                row_number=row_number,
                payload=payload,
                workflow_events=workflow_events,
                target=target,
                action=action,
            )
        )
    return ImportPlan(tuple(planned), tuple(errors), mapping)


def _normalize_row(source, panel_lookup):
    values = {key: _scalar(value) for key, value in source.items()}
    name = str(values.get("name") or "").strip()
    cover_number = str(values.get("cover_page_no") or "").strip()
    if not name:
        raise ValidationError({"name": "Document name is required."})
    if not cover_number:
        raise ValidationError({"cover_page_no": "Cover-page number is required."})

    panel = None
    panel_value = str(values.get("panel") or "").strip()
    if panel_value:
        panel = panel_lookup.get(panel_value.casefold())
        if panel is None:
            raise ValidationError({"panel": "Panel name or ATA is unknown for this project."})

    payload = {
        field: _list_value(values.get(field)) if field in LIST_FIELDS else values.get(field)
        for field in MODEL_FIELDS
        if values.get(field) not in (None, "")
    }
    payload["name"] = name
    payload["panel"] = panel.pk if panel else None
    payload["cover_page"] = {
        "number": cover_number,
        "issue": values.get("cover_page_issue"),
    }
    status = _normalize_status(values.get("status"))
    workflow_events, reconcile_workflow = _build_workflow_events(values, status)
    return {
        "id": str(values.get("id") or "").strip(),
        "payload": payload,
        "status": status,
        "workflow_events": workflow_events,
        "reconcile_workflow": reconcile_workflow,
    }


def _normalize_status(value):
    if value in (None, ""):
        return None
    status = re.sub(r"\s+", "_", str(value).strip().casefold().replace(".", ""))
    if status not in WORKFLOW_STATUSES:
        raise ValidationError({"status": "Unsupported workflow status."})
    return status


def _build_workflow_events(values, status):
    raw_effective_date = values.get("effective_date")
    raw_target_date = values.get("ubm_target_date")
    raw_delivery_date = values.get("ubm_delivery_date")
    has_target_date = raw_target_date not in (None, "")
    has_delivery_date = raw_delivery_date not in (None, "")

    if not status:
        if any(
            value not in (None, "")
            for value in (raw_effective_date, raw_target_date, raw_delivery_date)
        ):
            raise ValidationError(
                {"status": "A workflow status is required when a workflow date is provided."}
            )
        return (), False

    if has_delivery_date and not has_target_date:
        raise ValidationError(
            {"ubm_delivery_date": "A UBM target date is required before the delivery date."}
        )

    target_date = _parse_import_date(raw_target_date, "ubm_target_date")
    delivery_date = _parse_import_date(raw_delivery_date, "ubm_delivery_date")
    if delivery_date and status == "to_be_issued":
        raise ValidationError({"status": "The delivered status must follow To Be Issued."})

    if target_date:
        events = [PlannedWorkflowEvent("to_be_issued", target_date)]
        if status != "to_be_issued":
            current_date = delivery_date or _effective_date(raw_effective_date)
            if current_date < target_date:
                raise ValidationError(
                    {"ubm_delivery_date": "The delivery date cannot be before the UBM target date."}
                )
            events.append(PlannedWorkflowEvent(status, current_date))
        return tuple(events), True

    return (PlannedWorkflowEvent(status, _effective_date(raw_effective_date)),), False


def _effective_date(value):
    return _parse_import_date(value, "effective_date") or timezone.localdate()


def _parse_import_date(value, field):
    if value in (None, ""):
        return None
    parsed = parse_workflow_date(value)
    if parsed is None:
        raise ValidationError({field: "Use a supported calendar date."})
    return parsed


def _scalar(value):
    return value.strip() if isinstance(value, str) else value


def _list_value(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [part.strip() for part in re.split(r"[;,\n]", str(value)) if part.strip()]


def _payload_keys(values):
    payload = values["payload"]
    cover = _canonical_identity(payload["cover_page"]["number"])
    keys = {("name", cover, _canonical_identity(payload["name"]))}
    tech_doc_no = _canonical_identity(payload.get("tech_doc_no"))
    if tech_doc_no:
        keys.add(("tech_doc_no", cover, tech_doc_no))
    return frozenset(keys)


def _document_keys(document):
    cover = _canonical_identity(document.cover_page.number)
    keys = {("name", cover, _canonical_identity(document.name))}
    tech_doc_no = _canonical_identity(document.tech_doc_no)
    if tech_doc_no:
        keys.add(("tech_doc_no", cover, tech_doc_no))
    return frozenset(keys)


def _canonical_identity(value):
    return str(value or "").strip().casefold()


def _pending_workflow_events(target, normalized_row):
    requested = normalized_row["workflow_events"]
    if target is None:
        return tuple(event for event in requested if event.status != "unknown")
    if not normalized_row["reconcile_workflow"]:
        if not requested or requested[-1].status == target.status:
            return ()
        return requested

    existing = tuple(
        PlannedWorkflowEvent(event.status, event.effective_date)
        for event in target.import_workflow_events
    )
    if len(existing) > len(requested) or existing != requested[: len(existing)]:
        raise ValidationError(
            {
                "status_flow": (
                    "Imported workflow milestones conflict with the existing immutable history."
                )
            }
        )
    return requested[len(existing) :]


def _resolve_action(target, validated_data, workflow_events):
    if target is None:
        return "create"
    cover_data = validated_data.get("cover_page")
    if cover_data and (
        target.cover_page.number != cover_data["number"]
        or target.cover_page.issue != cover_data.get("issue")
    ):
        return "update"
    for field, value in validated_data.items():
        if field == "cover_page":
            continue
        comparable = value.pk if hasattr(value, "pk") else value
        current = getattr(target, f"{field}_id", None) if hasattr(value, "pk") else getattr(target, field)
        if current != comparable:
            return "update"
    if workflow_events:
        return "update"
    return "unchanged"


def plan_fingerprint(plan: ImportPlan) -> str:
    state = [
        {
            "row": row.row_number,
            "action": row.action,
            "target": str(row.target.pk) if row.target else None,
            "version": row.target.version if row.target else None,
            "identity": sorted(_payload_keys({"payload": row.payload})),
            "payload": row.payload,
            "workflow_events": row.workflow_events,
            "target_cover": (
                {
                    "id": str(row.target.cover_page_id),
                    "number": row.target.cover_page.number,
                    "issue": row.target.cover_page.issue,
                }
                if row.target
                else None
            ),
        }
        for row in plan.rows
    ]
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_confirmation(uploaded_file, user, project, plan):
    return signing.dumps(
        {
            "version": 1,
            "sha256": hash_upload(uploaded_file),
            "user_id": str(user.pk),
            "project": project.slug,
            "database_fingerprint": plan_fingerprint(plan),
        },
        salt=CONFIRMATION_SALT,
        compress=True,
    )


def verify_confirmation(token, uploaded_file, user, project):
    if not token:
        raise ValidationError(
            {"confirmation_token": "Import preview confirmation is required."},
            code="IMPORT_CONFIRMATION_REQUIRED",
        )
    try:
        payload = signing.loads(
            token,
            salt=CONFIRMATION_SALT,
            max_age=max(int(settings.COMPDOC_IMPORT_PREVIEW_TTL_SECONDS), 1),
        )
    except (signing.BadSignature, signing.SignatureExpired) as error:
        raise ValidationError(
            {"confirmation_token": "Import preview expired or is invalid."},
            code="IMPORT_PREVIEW_EXPIRED",
        ) from error
    identity_matches = all(
        (
            payload.get("version") == 1,
            payload.get("sha256") == hash_upload(uploaded_file),
            payload.get("user_id") == str(user.pk),
            payload.get("project") == project.slug,
            SHA256_PATTERN.fullmatch(str(payload.get("database_fingerprint", ""))),
        )
    )
    if not identity_matches:
        raise ValidationError(
            {"confirmation_token": "Workbook does not match the reviewed preview."},
            code="IMPORT_PREVIEW_MISMATCH",
        )
    return payload["database_fingerprint"]


def execute_plan(uploaded_file, project, request, expected_fingerprint):
    return execute_source_plan(
        project,
        request,
        expected_fingerprint,
        prepare_locked=lambda: prepare_plan(
            uploaded_file,
            project,
            request,
            lock_existing=True,
        ),
        audit_values={
            "source_filename": Path(str(uploaded_file.name)).name[:255],
            "source_size": max(int(uploaded_file.size or 0), 0),
            "source_sha256": hash_upload(uploaded_file),
        },
    )


def execute_source_plan(
    project,
    request,
    expected_fingerprint,
    *,
    prepare_locked,
    audit_values,
):
    """Execute one immutable tabular source through the shared import transaction."""

    audit = ImportAudit.objects.create(
        project=project,
        imported_by=request.user,
        request_id=str(getattr(request, "request_id", ""))[:64],
        **audit_values,
    )
    try:
        with transaction.atomic():
            plan = prepare_locked()
            if plan_fingerprint(plan) != expected_fingerprint:
                raise VersionConflict("Import targets changed after preview.")
            _apply_plan(plan, project, request, audit)
    except IntegrityError as error:
        _finish_failed_audit(audit, "IMPORT_TARGET_CONFLICT")
        raise VersionConflict("Import targets changed during confirmation.") from error
    except Exception as error:
        _finish_failed_audit(
            audit,
            str(getattr(error, "default_code", "") or "IMPORT_CONFIRM_FAILED")[:64],
        )
        raise

    audit.header_row = plan.mapping["header_row"]
    audit.mapped_columns = plan.mapping["mapped_columns"][:100]
    audit.unmapped_columns = plan.mapping["unmapped_columns"][:100]
    audit.missing_columns = plan.mapping["missing_columns"][:100]
    audit.total_rows = len(plan.rows) + len(plan.errors)
    counts = plan.counts
    for field, value in counts.items():
        setattr(audit, field, value)
    audit.error_summary = list(plan.errors)[:100]
    audit.status = (
        ImportAudit.Status.PARTIAL
        if plan.errors and (counts["created_count"] or counts["updated_count"])
        else ImportAudit.Status.FAILED
        if plan.errors
        else ImportAudit.Status.SUCCESS
    )
    audit.completed_at = timezone.now()
    audit.duration_ms = max(int((audit.completed_at - audit.started_at).total_seconds() * 1000), 0)
    audit.save()
    return audit, plan


def _apply_plan(plan, project, request, audit):
    for row in plan.rows:
        if row.action == "unchanged":
            continue
        serializer = ComplianceDocumentSerializer(
            row.target,
            data=row.payload,
            partial=row.target is not None,
            context={"request": request, "project": project},
        )
        serializer.is_valid(raise_exception=True)
        if row.target is None:
            document = serializer.save()
        else:
            document = update_document(
                project=project,
                document_id=row.target.pk,
                expected_version=row.target.version,
                serializer=serializer,
                user=request.user,
            )
        for workflow_event in row.workflow_events:
            document, _event = transition_document(
                project=project,
                document_id=document.pk,
                expected_version=document.version,
                new_status=workflow_event.status,
                effective_date=workflow_event.effective_date,
                next_action_due_date=None,
                reason=f"Compliance import {audit.pk}",
                user=request.user,
                source=WorkflowEvent.Source.IMPORT,
            )


def _finish_failed_audit(audit, code):
    completed_at = timezone.now()
    ImportAudit.objects.filter(pk=audit.pk).update(
        status=ImportAudit.Status.FAILED,
        error_summary=[{"row": None, "code": code, "fields": {}}],
        completed_at=completed_at,
        duration_ms=max(
            int((completed_at - audit.started_at).total_seconds() * 1000),
            0,
        ),
    )


def _row_error(row_number, error):
    return {
        "row": row_number,
        "code": "IMPORT_ROW_INVALID",
        "fields": error.detail,
    }
