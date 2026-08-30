from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    ComplianceDocument,
    CoverPage,
    DocumentPurgeAudit,
    ImportAudit,
    NotificationLog,
    NotificationPolicy,
    ReviewTask,
    TrackingProfile,
    WorkflowEvent,
)


class ImmutableEvidenceAdmin(admin.ModelAdmin):
    """Expose audit evidence without allowing history rewrites in admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ComplianceDocument)
class ComplianceDocumentAdmin(SimpleHistoryAdmin):
    """Keep document mutations on versioned domain endpoints and purge command."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(CoverPage, SimpleHistoryAdmin)
admin.site.register(WorkflowEvent, ImmutableEvidenceAdmin)
admin.site.register(ReviewTask, ImmutableEvidenceAdmin)
admin.site.register(TrackingProfile)
admin.site.register(NotificationLog, ImmutableEvidenceAdmin)
admin.site.register(NotificationPolicy, ImmutableEvidenceAdmin)
admin.site.register(ImportAudit, ImmutableEvidenceAdmin)
admin.site.register(DocumentPurgeAudit, ImmutableEvidenceAdmin)
