from django.contrib import admin

from .models import DccRecord, DccReminderDelivery, JiraIssueDraft, JiraIssueDraftEvent

admin.site.register(DccRecord)
admin.site.register(DccReminderDelivery)
admin.site.register(JiraIssueDraft)
admin.site.register(JiraIssueDraftEvent)
