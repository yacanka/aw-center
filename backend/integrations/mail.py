"""Linux-safe outbound mail adapter with no COM or ambient credential fallback."""

import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


class MailUnavailable(RuntimeError):
    """Raised when deployment has not enabled a supported mail transport."""


def parse_recipients(value):
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        source = value
    else:
        source = re.split(r"[;,]", str(value))
    return sorted({str(item).strip() for item in source if str(item).strip()})


def send_html_email(subject, html_body, to, *, cc=None, bcc=None, message_id=None):
    """Send one HTML message through the explicitly configured Django backend."""

    if settings.AWCENTER_MAIL_TRANSPORT != "django":
        raise MailUnavailable("Outbound mail is disabled.")
    recipients = parse_recipients(to)
    if not recipients:
        raise MailUnavailable("Outbound mail has no recipients.")
    headers = {"Message-ID": message_id} if message_id else None
    message = EmailMultiAlternatives(
        subject=str(subject)[:998],
        body="This message contains an HTML AW Center notification.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        cc=parse_recipients(cc),
        bcc=parse_recipients(bcc),
        headers=headers,
    )
    message.attach_alternative(str(html_body), "text/html")
    if message.send(fail_silently=False) < 1:
        raise MailUnavailable("Outbound mail was not accepted by the configured backend.")


def load_template_text(path):
    return path.read_text(encoding="utf-8")


def replace_placeholders(template, replacements):
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered
