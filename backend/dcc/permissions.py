from rest_framework.permissions import BasePermission


class DCCPermission(BasePermission):
    permission_map = {
        "GET": "dcc.view_jira_dcc",
        "POST": "dcc.add_jira_dcc",
        "PUT": "dcc.change_jira_dcc",
        "PATCH": "dcc.change_jira_dcc",
        "DELETE": "dcc.delete_jira_dcc",
    }

    def has_permission(self, request, view):
        required_permission = self.permission_map.get(request.method)
        if required_permission is None:
            return True

        return request.user.has_perm(required_permission)


class DCCAutomationPermission(BasePermission):
    """Allow Outlook/DCC creation side effects only to authorized DCC creators."""

    def has_permission(self, request, view):
        """Use the add-model permission consistently across POST and SSE GET steps."""

        return request.user.has_perm("dcc.add_jira_dcc")


class DCCTraceRefreshPermission(BasePermission):
    """Require both DCC read visibility and document creation authority."""

    def has_permission(self, request, view):
        """Keep trace discovery and regenerated output creation equally protected."""

        return request.user.has_perms(("dcc.view_jira_dcc", "dcc.add_jira_dcc"))


class IsDCCOwner(BasePermission):
    """Allow access only to DCC records created by the requesting user."""

    def has_object_permission(self, request, view, obj):
        return obj.created_by_id == request.user.id


class IsOwner(IsDCCOwner):
    """Backward-compatible alias for existing DCC owner checks."""
