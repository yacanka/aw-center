"""Safe, reusable helpers for reading Outlook message content."""

from pathlib import Path

import extract_msg

from jobs.contracts import JobExecutionFailure

MAX_BODY_CHARACTERS = 200_000


def open_message(source):
    """Open one Outlook message from a path or seekable binary source."""

    try:
        return extract_msg.openMsg(source)
    except Exception as error:
        raise JobExecutionFailure(
            "The Outlook message could not be read.", "OUTLOOK_MESSAGE_INVALID"
        ) from error


def message_summary(message):
    """Return bounded plain-text message metadata safe for JSON rendering."""

    return {
        "subject": text_value(message.subject, 500),
        "sender": text_value(message.sender, 500),
        "to": text_value(message.to, 5_000),
        "cc": text_value(message.cc, 5_000),
        "date": text_value(message.date, 200),
        "body_plain": text_value(message.body, MAX_BODY_CHARACTERS),
    }


def attachment_name(attachment):
    """Return the declared attachment filename without normalizing traversal."""

    value = getattr(attachment, "longFilename", None)
    value = value or getattr(attachment, "shortFilename", None) or "attachment"
    return str(value).strip() or "attachment"


def attachment_bytes(attachment):
    """Return attachment bytes or reject unsupported embedded objects."""

    value = getattr(attachment, "data", b"")
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, bytes):
        return value
    raise JobExecutionFailure(
        "The selected Outlook attachment has an unsupported format.",
        "OUTLOOK_ATTACHMENT_UNSUPPORTED",
    )


def safe_download_name(name):
    """Return a bounded basename suitable for Content-Disposition."""

    normalized = Path(str(name).replace("\\", "/")).name.strip()
    safe = "".join("_" if ord(character) < 32 or character in '<>:"/\\|?*' else character for character in normalized)
    return (safe[:180] or "attachment")


def close_message(message):
    """Close an extract-msg object when its implementation exposes close()."""

    close = getattr(message, "close", None)
    if callable(close):
        close()


def text_value(value, limit):
    """Normalize optional message fields and bound response memory."""

    return str(value or "")[:limit]
