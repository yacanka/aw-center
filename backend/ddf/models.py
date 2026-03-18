from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class DDF(models.Model):
    project = models.CharField()
    doc_name = models.CharField()
    doc_no = models.CharField()
    doc_issue = models.CharField()
    date = models.CharField()
    commentor = models.CharField()
    comments = models.JSONField(default=list)
    comment_types = models.JSONField(default=list)
    path = models.CharField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ddf")
    created_time = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return f"{self.doc_no} {self.doc_issue}"