"""Create editable Outlook MSG drafts without sending email."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore
except ImportError:
    pythoncom = None
    win32com = None

MAX_DRAFT_BYTES = 2 * 1024 * 1024
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
OL_FORMAT_HTML = 2
OL_MAIL_ITEM = 0
OL_MSG_UNICODE = 9


class MsgDraftUnavailable(RuntimeError):
    """Report that a valid Outlook draft could not be created."""


class MsgDraftInputError(ValueError):
    """Report unsafe or incomplete draft recipient input."""


def build_msg_draft(subject, html_body, recipients, cc_recipients=None):
    """Return a validated Unicode MSG draft containing editable mail fields."""

    recipient_line = _recipient_line(recipients)
    cc_line = _recipient_line(cc_recipients or [], required=False)
    try:
        with _initialized_com():
            mail_item = _create_mail_item(subject, html_body, recipient_line, cc_line)
            return _save_mail_item(mail_item)
    except MsgDraftInputError:
        raise
    except Exception as error:
        raise MsgDraftUnavailable("Outlook could not create the message draft.") from error


@contextmanager
def _initialized_com():
    if pythoncom is None or win32com is None:
        raise MsgDraftUnavailable("Outlook desktop automation is unavailable.")
    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def _create_mail_item(subject, html_body, recipient_line, cc_line):
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail_item = outlook.CreateItem(OL_MAIL_ITEM)
    mail_item.Subject = str(subject)
    mail_item.To = recipient_line
    mail_item.CC = cc_line
    mail_item.BodyFormat = OL_FORMAT_HTML
    mail_item.HTMLBody = str(html_body)
    return mail_item


def _save_mail_item(mail_item):
    with TemporaryDirectory(prefix="aw-msg-draft-") as directory:
        path = Path(directory) / "notification.msg"
        mail_item.SaveAs(str(path), OL_MSG_UNICODE)
        return _validated_draft_bytes(path)


def _validated_draft_bytes(path):
    content = path.read_bytes()
    if not content.startswith(OLE_SIGNATURE) or len(content) > MAX_DRAFT_BYTES:
        raise MsgDraftUnavailable("Outlook produced an invalid message draft.")
    return content


def _recipient_line(recipients, required=True):
    values = sorted({str(value).strip() for value in recipients if str(value).strip()})
    if required and not values:
        raise MsgDraftInputError("The message draft requires at least one recipient.")
    if any("\r" in value or "\n" in value or ";" in value for value in values):
        raise MsgDraftInputError("A message draft recipient is invalid.")
    return ";".join(values)
