from rest_framework.permissions import BasePermission


class DDFPermission(BasePermission):
    """Require Django model permissions for DDF API access."""

    permission_map = {
        "GET": "ddf.view_ddf",
        "POST": "ddf.add_ddf",
        "PUT": "ddf.change_ddf",
        "PATCH": "ddf.change_ddf",
        "DELETE": "ddf.delete_ddf",
    }

    def has_permission(self, request, view):
        required_permission = self.permission_map.get(request.method)
        if required_permission is None:
            return True
        return request.user.has_perm(required_permission)


class IsDDFOwner(BasePermission):
    """Allow access only to DDF records created by the requesting user."""

    def has_object_permission(self, request, view, obj):
        return obj.created_by_id == request.user.id
