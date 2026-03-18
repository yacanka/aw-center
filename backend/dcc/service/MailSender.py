import re

try:
    import win32com.client  # type: ignore
    import pythoncom  # type: ignore
except ImportError:
    win32com = None
    pythoncom = None

def html_to_text(html_file_path):
    with open(html_file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()

    return html_content

def replace_all_keys(text, replacements):
    for key, value in replacements.items():
        text = text.replace(key, value)  
    return text


def _parse_recipients(value):
    if not value:
        return []
    return [item.strip() for item in re.split(r"[;,]", str(value)) if item.strip()]


def SendMail(title, body, to, cc="", bcc=""):
    # Use Outlook COM when available (Windows desktop deployment).
    if win32com is not None and pythoncom is not None:
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail_item = outlook.CreateItem(0)

        mail_item.Subject = title
        mail_item.To = to
        mail_item.CC = cc
        mail_item.BCC = bcc
        mail_item.HTMLBody = body
        mail_item.Send()
        return

    # Cross-platform fallback: no-op for local/test environments without Outlook COM.
    recipients = _parse_recipients(to) + _parse_recipients(cc) + _parse_recipients(bcc)
    if recipients:
        print(f"[MailSender fallback] Outlook COM is unavailable. Skipping email send: {title}")

