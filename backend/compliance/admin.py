from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.utils.text import capfirst
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
from .purging import DocumentPurgeError, purge_document


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
    """Allow superusers to purge archived documents through a fenced path."""

    actions = None

    def has_delete_permission(self, request, obj=None):
        return bool(
            request.user.is_active
            and request.user.is_staff
            and request.user.is_superuser
            and (obj is None or obj.is_archived)
        )

    def get_deleted_objects(self, objs, request):
        deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request
        )
        allocation_label = CoverPageNumberAllocation._meta.verbose_name
        allocation_prefix = f"{capfirst(allocation_label)}:"
        # The purge service retains the allocation and clears its protected
        # document link before deletion, so it must not block admin confirmation.
        protected = [
            related
            for related in protected
            if not str(related).startswith(allocation_prefix)
        ]
        perms_needed.discard(allocation_label)
        return deleted_objects, model_count, perms_needed, protected

    def delete_model(self, request, obj):
        try:
            purge_document(
                document_id=obj.pk,
                expected_version=obj.version,
                operator=request.user,
                reason="Deleted through Django admin.",
            )
        except DocumentPurgeError as error:
            raise PermissionDenied(str(error)) from error


admin.site.register(CoverPage, ImmutableHistoryAdmin)
admin.site.register(CoverPageNumberAllocation, ImmutableEvidenceAdmin)
admin.site.register(WorkflowEvent, ImmutableEvidenceAdmin)
admin.site.register(ReviewTask, ImmutableEvidenceAdmin)
admin.site.register(TrackingProfile, ImmutableEvidenceAdmin)
admin.site.register(NotificationLog, ImmutableEvidenceAdmin)
admin.site.register(NotificationPolicy, ImmutableEvidenceAdmin)
admin.site.register(ImportAudit, ImmutableEvidenceAdmin)
admin.site.register(DocumentPurgeAudit, ImmutableEvidenceAdmin)
