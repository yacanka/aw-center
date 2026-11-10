from django.contrib import admin

from .workflow_models import JiraTrackedIssue, JiraReminderDelivery, JiraIssueDraft, JiraIssueDraftEvent

class TrackingAssignmentInline(admin.TabularInline):
    """Assignments remain governed by the parent tracking model permission."""

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("integrations.view_jiratrackedissue") or self.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("integrations.change_jiratrackedissue")

    def has_add_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)


class AssignedUserInline(TrackingAssignmentInline):
    model = JiraTrackedIssue.assigned_users.through
    extra = 0


class ProjectInline(TrackingAssignmentInline):
    model = JiraTrackedIssue.projects.through
    extra = 0


@admin.register(JiraTrackedIssue)
class JiraTrackedIssueAdmin(admin.ModelAdmin):
    # Explicit through models retain historical columns; inlines retain editing.
    inlines = (AssignedUserInline, ProjectInline)


admin.site.register(JiraReminderDelivery)
admin.site.register(JiraIssueDraft)
admin.site.register(JiraIssueDraftEvent)
