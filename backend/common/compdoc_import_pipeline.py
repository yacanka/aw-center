"""Preparation, validation, and upsert execution for CompDoc workbooks."""

from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException

from .compdoc_import import build_mapping_preview, choose_header_row, read_mapped_excel
from .compdoc_import_plan import (
    build_import_plan,
    summarize_import_plan,
)
from .compdoc_import_state import (
    CompDocImportDatabaseConflict,
    import_plan_fingerprint,
    require_matching_import_state,
)
from .compdoc_import_values import get_mappable_import_fields


class CompDocImportLimitExceeded(APIException):
    """Reject workbooks whose row count exceeds the configured bound."""

    status_code = 400
    default_code = "COMPDOC_IMPORT_ROW_LIMIT"

    def __init__(self, row_count, row_limit):
        """Store safe counts for audit finalization and response guidance."""

        self.row_count = row_count
        detail = f"Workbook has {row_count} rows; the limit is {row_limit}."
        super().__init__(detail, self.default_code)


@dataclass(frozen=True)
class PreparedImport:
    """Hold mapped workbook data and its safe preview metadata."""

    dataframe: object
    header_result: object
    preview: dict


def prepare_import(uploaded_file, model):
    """Detect headers and return a null-normalized mapped dataframe."""

    import pandas as pd

    fields = get_mappable_import_fields(model)
    header_result = choose_header_row(uploaded_file, pd, fields)
    uploaded_file.seek(0)
    preview_frame = pd.read_excel(uploaded_file, header=header_result.header_row_index)
    preview = build_mapping_preview(preview_frame.columns, header_result)
    uploaded_file.seek(0)
    dataframe = read_mapped_excel(uploaded_file, pd, header_result)
    dataframe = dataframe.astype(object).where(pd.notnull(dataframe), None)
    ensure_row_limit(dataframe)
    return PreparedImport(dataframe, header_result, preview)


def ensure_row_limit(dataframe):
    """Reject excessive rows before validation or database work begins."""

    row_limit = max(int(settings.AWCENTER_MAX_COMPDOC_IMPORT_ROWS), 1)
    if len(dataframe) > row_limit:
        raise CompDocImportLimitExceeded(len(dataframe), row_limit)


def preview_import(prepared, model, serializer_class):
    """Return a persistence-free action plan and safe row failures."""

    plan = build_import_plan(prepared, model, serializer_class)
    return summarize_import_plan(plan), import_plan_fingerprint(plan)


def execute_import(
    prepared, model, serializer_class, expected_fingerprint, actor=None, audit_id=None
):
    """Atomically persist a plan only while its signed database state remains current."""

    try:
        with transaction.atomic():
            plan = build_import_plan(prepared, model, serializer_class, lock_existing=True)
            require_matching_import_state(plan, expected_fingerprint)
            return execute_import_plan(plan, serializer_class, model, actor, audit_id)
    except IntegrityError as error:
        raise CompDocImportDatabaseConflict() from error


def execute_import_plan(plan, serializer_class, model=None, actor=None, audit_id=None):
    """Persist prevalidated plan rows inside the caller's atomic transaction."""

    result = summarize_import_plan(plan)
    created_count, updated_count = save_rows(
        plan.rows, serializer_class, model, actor, audit_id
    )
    result["created_count"] = created_count
    result["updated_count"] = updated_count
    return result


def save_rows(planned_rows, serializer_class, model=None, actor=None, audit_id=None):
    """Persist planned changes while skipping unchanged rows."""

    created_count = 0
    updated_count = 0
    for row in planned_rows:
        if row.action == "unchanged":
            continue
        save_row(row.instance, row.payload, serializer_class, model, actor, audit_id)
        if row.action == "update":
            updated_count += 1
        else:
            created_count += 1
    return created_count, updated_count


def save_row(instance, payload, serializer_class, model=None, actor=None, audit_id=None):
    """Persist one already planned row and propagate failures for batch rollback."""

    workflow = payload.get("status_flow") or []
    append = instance is not None and workflow != (instance.status_flow or [])
    safe_payload = {**payload, "status_flow": instance.status_flow} if append else payload
    serializer = serializer_class(instance, data=safe_payload)
    serializer.is_valid(raise_exception=True)
    document = serializer.save()
    if append and model and actor:
        events = workflow if not (instance.status_flow or []) else workflow[-1:]
        for event in events:
            document = _append_import_transition(
                model, document, event, actor, audit_id
            )
    elif instance is None and workflow and model and actor:
        _record_import_history(model, document, workflow, actor, audit_id)
    return document


def _append_import_transition(model, document, event, actor, audit_id):
    from common.compdoc_lifecycle import transition_document
    from common.compdoc_lifecycle_models import CompDocWorkflowEvent
    from common.compdoc_versions import latest_history_id
    from common.compdoc_workflow import parse_workflow_date

    reason = str(event.get("note") or f"Import audit {audit_id}")[:255]
    updated, _ = transition_document(
        model,
        document,
        {
            "source_history_id": latest_history_id(model, document.pk),
            "status": event["status"],
            "effective_date": parse_workflow_date(event["date"]),
            "next_action_due_date": None,
            "reason": reason,
        },
        actor,
        CompDocWorkflowEvent.Source.IMPORT,
    )
    return updated


def _record_import_history(model, document, workflow, actor, audit_id):
    from common.compdoc_lifecycle_models import CompDocWorkflowEvent
    from common.compdoc_workflow import parse_workflow_date

    previous = ""
    for sequence, event in enumerate(workflow, start=1):
        status = event["status"]
        CompDocWorkflowEvent.objects.create(
            project_slug=model._meta.app_label,
            document_id=document.pk,
            sequence=sequence,
            previous_status=previous,
            status=status,
            effective_date=parse_workflow_date(event["date"]),
            reason=str(event.get("note") or f"Import audit {audit_id}")[:255],
            source=CompDocWorkflowEvent.Source.IMPORT,
            actor=actor,
            actor_username=actor.get_username(),
        )
        previous = status
