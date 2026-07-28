from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    CompDocNotificationLog,
    CompDocNotificationPolicy,
    CompDocTrackingProfile,
    CoverPage,
)


admin.site.register(CoverPage, SimpleHistoryAdmin)


@admin.register(CompDocTrackingProfile)
class CompDocTrackingProfileAdmin(admin.ModelAdmin):
    """Expose opt-in state without resolving or storing email content."""

    list_display = (
        "project_slug",
        "document_id",
        "responsible_mode",
        "notification_enabled",
        "docproof_status",
        "updated_at",
    )
    list_filter = ("project_slug", "notification_enabled", "docproof_status")
    search_fields = ("document_id",)
    readonly_fields = ("created_at", "updated_at", "docproof_checked_at")


@admin.register(CompDocNotificationLog)
class CompDocNotificationLogAdmin(admin.ModelAdmin):
    """Expose content-free notification delivery evidence."""

    list_display = (
        "event_type",
        "status",
        "recipient_count",
        "attempt_count",
        "created_at",
    )
    list_filter = ("event_type", "status", "profile__project_slug")
    readonly_fields = tuple(field.name for field in CompDocNotificationLog._meta.fields)


@admin.register(CompDocNotificationPolicy)
class CompDocNotificationPolicyAdmin(admin.ModelAdmin):
    """Expose immutable project-policy revisions for audit review."""

    list_display = (
        "project_slug",
        "version",
        "is_active",
        "updated_by_username",
        "created_at",
    )
    list_filter = ("project_slug", "is_active")
    readonly_fields = tuple(field.name for field in CompDocNotificationPolicy._meta.fields)

    def has_add_permission(self, request):
        """Require policy revisions to pass through validation and version checks."""

        return False

    def has_change_permission(self, request, obj=None):
        """Keep policy revisions immutable in the generic admin."""

        return False

    def has_delete_permission(self, request, obj=None):
        """Retain policy history as audit evidence."""

        return False
