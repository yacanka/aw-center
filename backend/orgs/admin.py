from django.contrib import admin

from .models import (
    Panel,
    Person,
    Project,
    ProjectRoleAssignment,
    ResponsibleAssignment,
)


class GlobalProjectRoleAdminMixin:
    """Restrict project and role administration to the explicit global grant."""

    @staticmethod
    def _can_manage(request):
        return bool(
            request.user.is_active
            and request.user.is_staff
            and (
                request.user.is_superuser
                or request.user.has_perm("orgs.manage_project_roles")
            )
        )

    def has_module_permission(self, request):
        return self._can_manage(request)

    def has_view_permission(self, request, obj=None):
        return self._can_manage(request)

    def has_add_permission(self, request):
        return self._can_manage(request)

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request)

    def has_delete_permission(self, request, obj=None):
        return self._can_manage(request)


@admin.register(Project)
class ProjectAdmin(GlobalProjectRoleAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "enabled")
    list_filter = ("enabled",)
    search_fields = ("name", "slug")


@admin.register(ProjectRoleAssignment)
class ProjectRoleAssignmentAdmin(GlobalProjectRoleAdminMixin, admin.ModelAdmin):
    list_display = ("project", "domain", "role", "user", "group")
    list_filter = ("project", "domain", "role")
    autocomplete_fields = ("user", "group")


admin.site.register(Panel)
admin.site.register(Person)
admin.site.register(ResponsibleAssignment)
