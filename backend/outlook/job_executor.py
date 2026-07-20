"""Durable Outlook attachment extraction for connected workflows."""

from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile

from awcenter.file_security import UploadSecurityError, WORD_DOCUMENT_POLICY, validate_uploaded_file
from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult
from jobs.worker import update_progress

from .message_helpers import attachment_bytes, attachment_name, close_message, open_message


def execute_word_attachment_extraction(job):
    """Extract exactly one safe Word attachment from a private Outlook message."""

    input_path, output_path = materialize_job_input(job), temporary_output(".docx")
    message = None
    result_ready = False
    try:
        update_progress(job.id, 15, "Reading Outlook message.")
        message = open_message(str(input_path))
        attachment = select_word_attachment(message.attachments)
        name, content = validate_word_attachment(attachment)
        output_path.write_bytes(content)
        result_ready = True
        summary = {"attachment_name": name, "attachment_bytes": len(content)}
        return JobExecutionResult(output_path, name, "Word attachment extracted.", summary)
    finally:
        close_message(message)
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def select_word_attachment(attachments):
    """Select one unambiguous DOCX attachment without guessing user intent."""

    candidates = [item for item in attachments if attachment_suffix(item) == ".docx"]
    if not candidates:
        raise JobExecutionFailure(
            "The Outlook message contains no Word document attachment.",
            "OUTLOOK_WORD_ATTACHMENT_MISSING",
        )
    if len(candidates) > 1:
        raise JobExecutionFailure(
            "The Outlook message contains multiple Word attachments; keep only the document to analyze.",
            "OUTLOOK_WORD_ATTACHMENT_AMBIGUOUS",
        )
    return candidates[0]


def attachment_suffix(attachment):
    """Return the case-insensitive extension of one declared attachment name."""

    normalized = attachment_name(attachment).replace("\\", "/")
    return Path(normalized).suffix.lower()


def validate_word_attachment(attachment):
    """Validate extracted bytes as a safe OOXML Word document."""

    declared_name = attachment_name(attachment)
    if Path(declared_name.replace("\\", "/")).name != declared_name:
        raise JobExecutionFailure(
            "The Word attachment has an unsafe filename.", "OUTLOOK_ATTACHMENT_UNSAFE"
        )
    content = attachment_bytes(attachment)
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    upload = SimpleUploadedFile(declared_name, content, content_type=content_type)
    try:
        validate_uploaded_file(upload, WORD_DOCUMENT_POLICY)
    except UploadSecurityError as error:
        raise JobExecutionFailure(
            "The Word attachment failed file safety validation.", "OUTLOOK_ATTACHMENT_UNSAFE"
        ) from error
    return declared_name, content
