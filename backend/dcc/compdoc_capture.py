"""Canonical CompDoc fields embedded in immutable DCC outputs."""

CAPTURED_MODEL_FIELDS = (
    "name", "panel", "ata", "cover_page_no", "cover_page_issue",
    "tech_doc_no", "tech_doc_issue", "responsible", "status_flow",
    "tech_doc_no_2", "tech_doc_issue_2",
)


def captured_model_field_names(model):
    """Return concrete model fields required to reconstruct captured values."""

    available = {field.name for field in model._meta.fields}
    return tuple(name for name in CAPTURED_MODEL_FIELDS if name in available)


def captured_compdoc_values(document):
    """Return only values rendered into the DCC traceability register."""

    return {
        "name": scalar(document.name),
        "panel": scalar(document.panel),
        "ata": scalar(document.ata),
        "cover_page_no": scalar(document.cover_page_no),
        "cover_page_issue": scalar(document.cover_page_issue),
        "technical_documents": technical_documents(document),
        "responsible": scalar(document.responsible),
        "status": current_status(document.status_flow),
    }


def technical_documents(document):
    """Return primary and optional secondary technical-document references."""

    references = []
    for suffix in ("", "_2"):
        number = scalar(getattr(document, f"tech_doc_no{suffix}", ""))
        issue = scalar(getattr(document, f"tech_doc_issue{suffix}", ""))
        if number or issue:
            references.append({"number": number, "issue": issue})
    return references


def current_status(status_flow):
    """Return the last valid compliance status identifier."""

    if not isinstance(status_flow, list):
        return ""
    for event in reversed(status_flow[-100:]):
        if isinstance(event, dict) and event.get("status"):
            return scalar(event["status"])
    return ""


def scalar(value):
    """Return a stable stripped scalar string."""

    return "" if value is None else str(value).strip()
