"""Lightweight public contracts for explainable document analysis."""

from uuid import UUID

from jobs.contracts import JobExecutionFailure

ANALYSIS_CHECKS = {
    "compliance_documents": "Does the document contain a list of compliance documents?",
    "abbreviations": "Does the document contain an abbreviations table?",
    "attachments": "Does the document contain an attachments table or section?",
    "revision_history": "Does the document contain revision or change history?",
    "approvals": "Does the document contain approval or signature information?",
}
CUSTOM_CHECK_PREFIX = "custom:"
MAX_CUSTOM_CHECKS = 20
MAX_QUESTION_LENGTH = 500


class AnalysisChecklistError(ValueError):
    """Represent invalid user-owned analysis checklist data."""


def normalize_custom_checks(values):
    """Validate persisted custom checks and return their canonical representation."""

    if not isinstance(values, list) or len(values) > MAX_CUSTOM_CHECKS:
        raise AnalysisChecklistError(f"Save at most {MAX_CUSTOM_CHECKS} custom questions.")
    normalized = [normalize_custom_check(value) for value in values]
    identifiers = [item["id"] for item in normalized]
    if len(identifiers) != len(set(identifiers)):
        raise AnalysisChecklistError("Custom question identifiers must be unique.")
    return normalized


def normalize_custom_check(value):
    """Validate one custom check without accepting arbitrary persisted fields."""

    if not isinstance(value, dict):
        raise AnalysisChecklistError("Each custom question must be an object.")
    try:
        identifier = str(UUID(str(value.get("id", ""))))
    except ValueError as error:
        raise AnalysisChecklistError("Custom question identifier is invalid.") from error
    raw_question = value.get("question")
    if not isinstance(raw_question, str):
        raise AnalysisChecklistError("Question text is required.")
    question = " ".join(raw_question.split())
    if not question or len(question) > MAX_QUESTION_LENGTH:
        raise AnalysisChecklistError(
            f"Questions must contain 1 to {MAX_QUESTION_LENGTH} characters."
        )
    return {"id": identifier, "question": question}


def validate_check_ids(values, custom_checks=None):
    """Validate and deduplicate default or owner-approved analyzer checks."""

    requested = list(ANALYSIS_CHECKS) if values is None else values
    if not isinstance(requested, list) or not requested:
        raise JobExecutionFailure(
            "Select at least one analysis check.", "WORD_ANALYZER_CHECKS_INVALID"
        )
    normalized = list(dict.fromkeys(str(value) for value in requested))
    custom = normalize_custom_checks(custom_checks or [])
    allowed = set(ANALYSIS_CHECKS) | {
        f"{CUSTOM_CHECK_PREFIX}{item['id']}" for item in custom
    }
    if len(normalized) > len(ANALYSIS_CHECKS) + MAX_CUSTOM_CHECKS or any(
        value not in allowed for value in normalized
    ):
        raise JobExecutionFailure(
            "Unsupported analysis check selected.", "WORD_ANALYZER_CHECKS_INVALID"
        )
    return normalized


def selected_custom_checks(check_ids, custom_checks):
    """Return an immutable snapshot of custom questions selected for one job."""

    normalized = normalize_custom_checks(custom_checks)
    selected = set(validate_check_ids(check_ids, normalized))
    return [
        item for item in normalized if f"{CUSTOM_CHECK_PREFIX}{item['id']}" in selected
    ]


def resolve_analysis_checks(check_ids, custom_checks=None):
    """Resolve validated identifiers to private retrieval queries."""

    custom = normalize_custom_checks(custom_checks or [])
    identifiers = validate_check_ids(check_ids, custom)
    questions = {f"{CUSTOM_CHECK_PREFIX}{item['id']}": item["question"] for item in custom}
    return [
        {"id": identifier, "title": ANALYSIS_CHECKS.get(identifier, questions.get(identifier))}
        for identifier in identifiers
    ]
