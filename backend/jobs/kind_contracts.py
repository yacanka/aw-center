"""Stable job-kind parameters shared by enqueue and executor adapters."""

WORD_TRANSLATION_LABELS = {"tr2en": "TR-EN", "en2tr": "EN-TR"}
SUPPORTED_TRANSLATIONS = frozenset(WORD_TRANSLATION_LABELS)
DEFAULT_WORD_ANALYSIS_CHECK_IDS = (
    "compliance_documents",
    "abbreviations",
    "attachments",
    "revision_history",
    "approvals",
)
