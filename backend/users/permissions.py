from rest_framework.permissions import BasePermission


class DjangoModelPermission(BasePermission):
    """Require Django model permissions for explicit APIView resources."""

    permission_map = {}

    def has_permission(self, request, view):
        """Return whether the authenticated user owns the method permission."""
        if not request.user.is_authenticated or not request.user.is_active:
            return False
        if not (request.user.is_staff or request.user.is_superuser):
            return False
        required_permission = self.permission_map.get("GET" if request.method == "HEAD" else request.method)
        if required_permission is None:
            return request.method == "OPTIONS"

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

    def has_permission(self, request, view):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not request.user.is_superuser:
            return False
        return super().has_permission(request, view)

    permission_map = {
        "GET": "auth.view_group",
        "POST": "auth.add_group",
        "PUT": "auth.change_group",
        "PATCH": "auth.change_group",
        "DELETE": "auth.delete_group",
    }


class CanInviteUsers(BasePermission):
    """Require both staff status and explicit user-creation authority."""

    def has_permission(self, request, view):
        """Return whether the caller may create account invitations."""

        return bool(
            request.user.is_authenticated
            and request.user.is_active
            and (request.user.is_staff or request.user.is_superuser)
            and request.user.has_perm("auth.add_user")
        )
