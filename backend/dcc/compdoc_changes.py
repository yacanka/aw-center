"""Explain changes to fields captured by immutable DCC outputs."""

from .compdoc_capture import captured_compdoc_values, captured_model_field_names

CAPTURED_FIELD_METADATA = (
    ("cover_page_no", "Cover page number", "reference"),
    ("cover_page_issue", "Cover page issue", "reference"),
    ("technical_documents", "Technical document references", "reference"),
    ("status", "Workflow status", "workflow"),
    ("name", "Document name", "identity"),
    ("panel", "Panel", "classification"),
    ("ata", "ATA chapter", "classification"),
    ("responsible", "Responsible", "ownership"),
)


def compare_captured_compdoc(current_document, source_document):
    """Return a content-free comparison of DCC-visible CompDoc fields."""

    if source_document is None:
        return comparison_result("unavailable", [])
    current_values = captured_compdoc_values(current_document)
    source_values = captured_compdoc_values(source_document)
    changes = [
        field_change(code, label, category)
        for code, label, category in CAPTURED_FIELD_METADATA
        if current_values[code] != source_values[code]
    ]
    return comparison_result("changed" if changes else "unchanged", changes)


def load_trace_source_changes(model, current_document, traces):
    """Bulk-load captured history rows and compare every trace without N+1 queries."""

    history_ids = {trace.source_history_id for trace in traces if trace.source_history_id}
    histories = model.history.model.objects.filter(
        id=current_document.pk, history_id__in=history_ids
    ).only("id", "history_id", *captured_model_field_names(model))
    by_history_id = {history.history_id: history for history in histories}
    return {
        trace.id: compare_captured_compdoc(
            current_document, by_history_id.get(trace.source_history_id)
        )
        for trace in traces
    }


def comparison_result(status, changed_fields):
    """Return the stable public source-change contract."""

    return {
        "comparison_status": status,
        "captured_fields_changed": bool(changed_fields),
        "changed_field_count": len(changed_fields),
        "changed_fields": changed_fields,
    }


def field_change(code, label, category):
    """Return one value-free changed-field descriptor."""

    return {"code": code, "label": label, "category": category}
