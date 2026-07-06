from rest_framework.permissions import BasePermission


class DjangoModelPermission(BasePermission):
    """Require Django model permissions for explicit APIView resources."""

    permission_map = {}

    def has_permission(self, request, view):
        """Return whether the authenticated user owns the method permission."""
        required_permission = self.permission_map.get(request.method)
        if required_permission is None:
            return True

        return request.user.has_perm(required_permission)


class UserPermission(DjangoModelPermission):
    """Authorize user-management endpoints through auth user permissions."""

    permission_map = {
        "GET": "auth.view_user",
        "POST": "auth.add_user",
        "PUT": "auth.change_user",
        "PATCH": "auth.change_user",
        "DELETE": "auth.delete_user",
    }


class GroupPermission(DjangoModelPermission):
    """Authorize role/group endpoints through auth group permissions."""

    permission_map = {
        "GET": "auth.view_group",
        "POST": "auth.add_group",
        "PUT": "auth.change_group",
        "PATCH": "auth.change_group",
        "DELETE": "auth.delete_group",
    }
