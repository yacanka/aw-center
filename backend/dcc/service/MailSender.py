import re
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

try:
    import win32com.client  # type: ignore
    import pythoncom  # type: ignore
except ImportError:
    win32com = None
    pythoncom = None

LOGGER = logging.getLogger(__name__)

def html_to_text(html_file_path):
    with open(html_file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()

    return html_content

def replace_all_keys(text, replacements):
    for key, value in replacements.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _parse_recipients(value):
    if not value:
        return []
    return [item.strip() for item in re.split(r"[;,]", str(value)) if item.strip()]


def SendMail(title, body, to, cc="", bcc=""):
    """Send an HTML email through Outlook and report delivery availability."""

    if settings.AWCENTER_MAIL_TRANSPORT == "django":
        return _send_with_django(title, body, to, cc, bcc)
    if settings.AWCENTER_MAIL_TRANSPORT == "disabled":
        return False
    if win32com is not None and pythoncom is not None:
        return _send_with_outlook(title, body, to, cc, bcc)
    _warn_unavailable(to, cc, bcc)
    return False


def _send_with_outlook(title, body, to, cc, bcc):
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail_item = outlook.CreateItem(0)
    mail_item.Subject = title
    mail_item.To = to
    mail_item.CC = cc
    mail_item.BCC = bcc
    mail_item.HTMLBody = body
    mail_item.Send()
    return True


def _warn_unavailable(to, cc, bcc):
    recipients = _parse_recipients(to) + _parse_recipients(cc) + _parse_recipients(bcc)
    if recipients:
        LOGGER.warning(
            "Outlook COM is unavailable; email delivery was skipped.",
            extra={"recipient_count": len(recipients)},
        )


def _send_with_django(title, body, to, cc, bcc):
    recipients = _parse_recipients(to)
    if not recipients:
        return False
    message = EmailMultiAlternatives(
        subject=title,
        body="This message contains an HTML compliance notification.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        cc=_parse_recipients(cc),
        bcc=_parse_recipients(bcc),
    )
    message.attach_alternative(body, "text/html")
    return message.send(fail_silently=False) > 0
