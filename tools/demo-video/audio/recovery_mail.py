"""Deliver one demo password-reset message to memory and pass its link over a private pipe."""
import os
from html.parser import HTMLParser
from pathlib import Path
import stat
import sys
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parents[3]
RECIPIENT='d10005@example.invalid'


class ResetLinks(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[]

    def handle_starttag(self, tag, attributes):
        if tag=='a':
            self.links.extend(value for name,value in attributes if name=='href' and value)


def deliver_in_memory():
    sys.path.insert(0,str(ROOT/'tools/demo-video/backend_demo'))
    from run import prepare
    prepare(False)
    from django.conf import settings
    from django.core import mail
    from django.test import override_settings
    from users.models import PasswordResetDelivery
    from users.password_reset_notifications import claim_password_reset_deliveries,deliver_password_reset
    if settings.EMAIL_BACKEND!='django.core.mail.backends.locmem.EmailBackend':
        raise RuntimeError('This delivery requires the isolated memory backend.')
    allowed=PasswordResetDelivery.objects.filter(user__username='D10005',user__email=RECIPIENT)
    exclude=list(PasswordResetDelivery.objects.exclude(id__in=allowed.values('id')).values_list('id',flat=True))
    claims=claim_password_reset_deliveries(limit=1,exclude_ids=exclude)
    if len(claims)!=1 or not allowed.filter(pk=claims[0][0]).exists():
        raise RuntimeError('No delivery is ready for the isolated demo recipient.')
    with override_settings(AWCENTER_MAIL_TRANSPORT='django'):
        if deliver_password_reset(*claims[0])!=PasswordResetDelivery.Status.SENT:
            raise RuntimeError('The demo delivery did not complete.')
    if len(mail.outbox)!=1 or mail.outbox[0].to!=[RECIPIENT]:
        raise RuntimeError('Unexpected isolated mailbox contents.')
    parser=ResetLinks()
    for content,typ in mail.outbox[0].alternatives:
        if typ=='text/html':parser.feed(content)
    for link in parser.links:
        url=urlsplit(link)
        if (url.scheme,url.netloc,url.path,url.query)==('http','127.0.0.1:18765','/app/login','') and set(parse_qs(url.fragment))=={'uid','token'}:
            return link
    raise RuntimeError('The isolated message did not contain the expected reset fragment.')


if __name__=='__main__':
    # A standalone terminal invocation must never reveal a usable capability, even when redirected.
    try:
        mode=os.fstat(3).st_mode
    except OSError:
        raise SystemExit('Private caller pipe required.') from None
    if not (stat.S_ISSOCK(mode) or stat.S_ISFIFO(mode)):
        raise SystemExit('Private caller pipe required.')
    with os.fdopen(3,'wb') as pipe:
        pipe.write(deliver_in_memory().encode('utf-8'))
