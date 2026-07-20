from django.contrib import admin
from .models import DccCompdocTrace, JIRA_DCC, JiraIssueDraft, JiraIssueDraftEvent

admin.site.register(JIRA_DCC)
admin.site.register(JiraIssueDraft)
admin.site.register(JiraIssueDraftEvent)
admin.site.register(DccCompdocTrace)
