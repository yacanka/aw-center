"""Lightweight public contracts for explainable document analysis."""

from jobs.contracts import JobExecutionFailure

ANALYSIS_CHECKS = {
    "compliance_documents": "Does the document contain a list of compliance documents?",
    "abbreviations": "Does the document contain an abbreviations table?",
    "attachments": "Does the document contain an attachments table or section?",
    "revision_history": "Does the document contain revision or change history?",
    "approvals": "Does the document contain approval or signature information?",
}


def validate_check_ids(values):
    """Validate and deduplicate an allowlisted analyzer checklist."""

    requested = list(ANALYSIS_CHECKS) if values is None else values
    if not isinstance(requested, list) or not requested:
        raise JobExecutionFailure(
            "Select at least one analysis check.", "WORD_ANALYZER_CHECKS_INVALID"
        )
    normalized = list(dict.fromkeys(str(value) for value in requested))
    has_unknown_check = any(value not in ANALYSIS_CHECKS for value in normalized)
    if len(normalized) > len(ANALYSIS_CHECKS) or has_unknown_check:
        raise JobExecutionFailure(
            "Unsupported analysis check selected.", "WORD_ANALYZER_CHECKS_INVALID"
        )
    return normalized
