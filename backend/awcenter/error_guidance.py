"""Safe recovery guidance for machine-readable AW Center errors."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorGuidance:
    """Describe whether and how a failed operation should be retried."""

    retryable: bool
    recovery_hint: str

    def as_payload(self):
        """Return the public API representation."""

        return {"retryable": self.retryable, "recovery_hint": self.recovery_hint}


_EXACT_GUIDANCE = {
    "AUTHENTICATION_FAILED": ErrorGuidance(
        False, "Verify your credentials and sign in again."
    ),
    "FORBIDDEN": ErrorGuidance(False, "Request the required permission from an administrator."),
    "NOT_FOUND": ErrorGuidance(False, "Refresh the page and verify that the resource still exists."),
    "PARSE_ERROR": ErrorGuidance(False, "Check the input format and submit a valid document."),
    "THROTTLED": ErrorGuidance(True, "Wait briefly before trying again."),
    "VALIDATION_ERROR": ErrorGuidance(False, "Correct the highlighted fields and submit again."),
    "UPLOAD_REQUIRED": ErrorGuidance(False, "Select a file before starting the operation."),
    "UPLOAD_EMPTY": ErrorGuidance(False, "Select a non-empty file and try again."),
    "UPLOAD_TOO_LARGE": ErrorGuidance(False, "Reduce the file size or split it into smaller inputs."),
    "UPLOAD_TYPE_UNSUPPORTED": ErrorGuidance(False, "Choose one of the supported file formats."),
    "UPLOAD_UNSAFE_NAME": ErrorGuidance(False, "Rename the file using a simple safe filename."),
    "COMPDOC_IMPORT_CONFIRMATION_REQUIRED": ErrorGuidance(
        False, "Review the detected mappings before confirming the import."
    ),
    "COMPDOC_IMPORT_COLUMNS_MISSING": ErrorGuidance(
        False, "Add the listed required columns and upload the workbook again."
    ),
    "COMPDOC_IMPORT_PREVIEW_EXPIRED": ErrorGuidance(
        False, "Preview the workbook again before confirming the import."
    ),
    "COMPDOC_IMPORT_PREVIEW_MISMATCH": ErrorGuidance(
        False, "Preview the exact workbook you want to import, then confirm it."
    ),
    "IDEMPOTENCY_CONFLICT": ErrorGuidance(False, "Refresh the job list before submitting new data."),
    "INVITATION_EXPIRED": ErrorGuidance(False, "Ask an administrator to create a new invitation."),
    "INVITATION_REVOKED": ErrorGuidance(False, "Ask an administrator for the newest invitation."),
    "INVITATION_USED": ErrorGuidance(False, "Sign in with the account created from this invitation."),
    "INVITATION_SESSION_ACTIVE": ErrorGuidance(False, "Sign out before accepting another invitation."),
    "JIRA_DRAFT_VERSION_CONFLICT": ErrorGuidance(
        False, "Refresh the draft and review the newest version before continuing."
    ),
    "JIRA_DRAFT_STATE_CONFLICT": ErrorGuidance(
        False, "Refresh the draft and review its current approval state."
    ),
    "JIRA_DRAFT_PUBLISH_FAILED": ErrorGuidance(
        True, "Verify the JIRA session and availability, then safely retry publication."
    ),
    "JIRA_DRAFT_PREFLIGHT_BLOCKED": ErrorGuidance(
        False, "Complete the listed JIRA fields, save the draft, and approve the new version."
    ),
    "JIRA_DRAFT_PREFLIGHT_UNAVAILABLE": ErrorGuidance(
        True, "Verify the temporary JIRA session and project access, then retry the check."
    ),
    "DCC_JIRA_UNAVAILABLE": ErrorGuidance(
        True, "Verify the temporary JIRA session and JIRA availability, then retry."
    ),
    "DCC_CAPTURE_FAILED": ErrorGuidance(
        True, "Retry once; use the request reference if JIRA capture still fails."
    ),
    "DCC_PREVIEW_EXPIRED": ErrorGuidance(
        False, "Capture and review the current JIRA source again before queueing the document."
    ),
    "DCC_PREVIEW_NOT_CONFIRMABLE": ErrorGuidance(
        False, "Create a new DCC preview and review its current state."
    ),
    "DCC_TEMPLATE_UNAVAILABLE": ErrorGuidance(
        False, "Ask an administrator to deploy the registered project DOCX template."
    ),
    "DCC_RENDER_FAILED": ErrorGuidance(
        False, "Ask an administrator to validate the registered template placeholders."
    ),
    "TEAMCENTER_NOT_CONFIGURED": ErrorGuidance(False, "Ask an administrator to configure Teamcenter."),
    "TEAMCENTER_AUTH_FAILED": ErrorGuidance(False, "Ask an administrator to verify Teamcenter credentials."),
    "DOORS_UNAVAILABLE": ErrorGuidance(False, "Start or configure the DOORS client, then retry."),
    "WORD_MODEL_UNAVAILABLE": ErrorGuidance(False, "Ask an administrator to deploy the local AI model."),
    "WORD_ANALYZER_MODEL_UNAVAILABLE": ErrorGuidance(
        False, "Ask an administrator to deploy the analyzer models."
    ),
    "JOB_TIMEOUT": ErrorGuidance(True, "Retry once with a smaller input or a longer worker timeout."),
    "JOB_LEASE_EXPIRED": ErrorGuidance(True, "Retry the job after worker availability is restored."),
    "JOB_EXECUTION_FAILED": ErrorGuidance(True, "Retry once; use the reference if it fails again."),
    "JOB_INPUT_CORRUPT": ErrorGuidance(False, "Upload the original input again and create a new job."),
    "JOB_OUTPUT_TOO_LARGE": ErrorGuidance(False, "Reduce the requested output size and create a new job."),
}

_PREFIX_GUIDANCE = (
    ("COMPDOC_IMPORT_", ErrorGuidance(False, "Review the import audit and correct the workbook.")),
    ("UPLOAD_ARCHIVE_", ErrorGuidance(False, "Use a safe, unencrypted archive with fewer entries.")),
    ("UPLOAD_", ErrorGuidance(False, "Review the file requirements and choose another input.")),
    ("INVITATION_", ErrorGuidance(False, "Ask an administrator to review the invitation status.")),
    ("TEAMCENTER_", ErrorGuidance(True, "Check Teamcenter availability, then retry once.")),
    ("DOORS_", ErrorGuidance(True, "Check the DOORS client connection, then retry once.")),
    ("JIRA_", ErrorGuidance(True, "Check the JIRA session and attachment, then retry once.")),
    ("DCC_", ErrorGuidance(False, "Review the JIRA task, project mapping, and DCC fields.")),
    ("JOB_", ErrorGuidance(False, "Open Job Center and review the job details.")),
    ("WORD_", ErrorGuidance(False, "Review the document and local model configuration.")),
    ("COVER_PAGE_", ErrorGuidance(False, "Correct the spreadsheet rows and create a new job.")),
    ("SUBTASK_FIELDS_", ErrorGuidance(False, "Review the JIRA issue type and required fields.")),
)


def guidance_for(error_code, status_code):
    """Resolve safe guidance by exact code, domain prefix, or HTTP status."""

    normalized_code = str(error_code or "ERROR").upper()
    exact = _EXACT_GUIDANCE.get(normalized_code)
    if exact:
        return exact
    for prefix, guidance in _PREFIX_GUIDANCE:
        if normalized_code.startswith(prefix):
            return guidance
    return _status_guidance(status_code)


def _status_guidance(status_code):
    if status_code == 401:
        return _EXACT_GUIDANCE["AUTHENTICATION_FAILED"]
    if status_code == 403:
        return _EXACT_GUIDANCE["FORBIDDEN"]
    if status_code == 404:
        return _EXACT_GUIDANCE["NOT_FOUND"]
    if status_code == 429:
        return _EXACT_GUIDANCE["THROTTLED"]
    if status_code >= 500:
        return ErrorGuidance(True, "Retry once; use the support reference if it fails again.")
    if status_code == 409:
        return ErrorGuidance(False, "Refresh the current state before deciding the next action.")
    return ErrorGuidance(False, "Review the request and use the support reference if needed.")
