from django.contrib import admin

from .models import DccRecord, JiraIssueDraft, JiraIssueDraftEvent

admin.site.register(DccRecord)
admin.site.register(JiraIssueDraft)
admin.site.register(JiraIssueDraftEvent)
