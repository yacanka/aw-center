RECOVERY_HINTS = {
    "WORD_MODEL_UNAVAILABLE": "Ask an administrator to deploy the configured local translation model, then retry.",
    "WORD_ANALYZER_MODEL_UNAVAILABLE": "Ask an administrator to deploy both configured analyzer models, then retry.",
    "WORD_ANALYZER_EXECUTION_FAILED": "Verify the local analyzer runtime and model health, then retry.",
    "WORD_ANALYZER_EMPTY": "Upload a document containing readable paragraphs or table content.",
    "WORD_ANALYZER_UNIT_LIMIT": "Split the document into smaller sections and analyze them separately.",
    "JOB_TIMEOUT": "Retry once; if it repeats, reduce input size or ask an administrator to review worker capacity.",
    "JOB_LEASE_EXPIRED": "The worker stopped responding. Retry after worker availability returns.",
    "JOB_INPUT_CORRUPT": "Upload the source file again; the stored artifact failed its integrity check.",
    "JOB_OUTPUT_TOO_LARGE": "Reduce input size or output quality, then create a new job.",
    "COVER_PAGE_COLUMNS_MISSING": "Add every required workbook column and upload a corrected file.",
    "COVER_PAGE_ROWS_EMPTY": "Provide at least one row with both cover-page number and issue.",
    "COVER_PAGE_ROW_LIMIT": "Split the workbook into smaller batches and queue each batch separately.",
    "MEDIA_CONVERSION_FAILED": "Verify that the selected output format is compatible with the source media.",
}


def recovery_hint(error_code):
    """Return a sanitized actionable hint for a stable worker error code."""

    return RECOVERY_HINTS.get(error_code, "Review the job audit history and request ID before retrying.")
