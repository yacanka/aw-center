from rest_framework.permissions import BasePermission

class UserPermission(BasePermission):
    permission_map = {
        "GET": "auth.view_user",
        # "POST": "auth.add_user",
        "PUT": "auth.change_user",
        "PATCH": "auth.change_user",
        "DELETE": "auth.delete_user",
    }

    def has_permission(self, request, view):
        required_permission = self.permission_map.get(request.method)
        if required_permission is None:
            return True
        
        return request.user.has_perm(required_permission)