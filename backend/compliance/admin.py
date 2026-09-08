from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    ComplianceDocument,
    CoverPage,
    CoverPageNumberAllocation,
    DocumentPurgeAudit,
    ImportAudit,
    NotificationLog,
    NotificationPolicy,
    ReviewTask,
    TrackingProfile,
    WorkflowEvent,
)


class ReadOnlyAdminMixin:
    """Expose audit evidence without allowing history rewrites in admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ImmutableEvidenceAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Expose audit evidence without allowing history rewrites in admin."""


class ImmutableHistoryAdmin(ReadOnlyAdminMixin, SimpleHistoryAdmin):
    """Expose historical state while preserving versioned domain mutations."""


@admin.register(ComplianceDocument)
class ComplianceDocumentAdmin(ImmutableHistoryAdmin):
    """Keep document mutations on versioned domain endpoints and purge command."""


admin.site.register(CoverPage, ImmutableHistoryAdmin)
admin.site.register(CoverPageNumberAllocation, ImmutableEvidenceAdmin)
admin.site.register(WorkflowEvent, ImmutableEvidenceAdmin)
admin.site.register(ReviewTask, ImmutableEvidenceAdmin)
admin.site.register(TrackingProfile, ImmutableEvidenceAdmin)
admin.site.register(NotificationLog, ImmutableEvidenceAdmin)
admin.site.register(NotificationPolicy, ImmutableEvidenceAdmin)
admin.site.register(ImportAudit, ImmutableEvidenceAdmin)
admin.site.register(DocumentPurgeAudit, ImmutableEvidenceAdmin)
