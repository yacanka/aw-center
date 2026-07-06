from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class JIRA_DCC(models.Model):
    class Meta:
        ordering = ["-created_time", "issue", "id"]

    issue = models.CharField(max_length=255)
    ecd_name = models.CharField(max_length=255)
    dcc_path = models.CharField(max_length=512, verbose_name="DCC Folder Path", null=True, blank=True, )
    active = models.BooleanField(help_text="If it is active, then it will check the issue on JIRA")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dcc")
    created_time = models.DateTimeField(default=timezone.now, editable=False)
    last_reminder_mail_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

    def __str__(self):
        return self.issue
