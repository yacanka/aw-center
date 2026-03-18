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

class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        print(obj.created_by, request.user)
        return obj.created_by == request.user    