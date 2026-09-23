import time

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.models import Group, Permission
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Prefetch, Q
from orgs.models import ProjectRoleAssignment
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import GroupPermission, UserPermission
from .password_reset_notifications import pad_password_reset_response
from .throttles import (
    PasswordResetAccountThrottle,
    PasswordResetAddressThrottle,
    PasswordResetCapabilityThrottle,
    PasswordResetConfirmAddressThrottle,
)
from awcenter.pagination import paginated_response
from .serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    GroupSerializer,
    PermissionSerializer,
    UserPreferencesSerializer,
    UserAdministrationSerializer,
)

User = get_user_model()


class UserView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), UserPermission()]

    def _user_queryset(self):
        return User.objects.select_related("preferences").prefetch_related(
            "user_permissions__content_type",
            "groups__permissions__content_type",
            Prefetch("project_role_assignments", queryset=ProjectRoleAssignment.objects.select_related("project")),
            Prefetch("groups__project_role_assignments", queryset=ProjectRoleAssignment.objects.select_related("project")),
        )

    def get(self, request, pk=None):
        if pk:
            user = get_object_or_404(self._user_queryset(), pk=pk)
            serializer = UserAdministrationSerializer(user, context={"request": request})
            return Response(serializer.data)

        users = self._user_queryset().order_by("id")
        search = request.query_params.get("search", "").strip()[:200]
        if search:
            users = users.filter(Q(username__icontains=search) | Q(email__icontains=search)
                                 | Q(first_name__icontains=search) | Q(last_name__icontains=search))
        account = request.query_params.get("account")
        if account == "active":
            users = users.filter(is_active=True)
        elif account == "inactive":
            users = users.filter(is_active=False)
        elif account == "admin":
            users = users.filter(Q(is_staff=True) | Q(is_superuser=True))
        first_name = request.query_params.get("first_name")
        last_name = request.query_params.get("last_name")
        username = request.query_params.get("username")
        email = request.query_params.get("email")
        if first_name:
            users = users.filter(first_name__icontains=first_name)
        if last_name:
            users = users.filter(last_name__icontains=last_name)
        if username:
            users = users.filter(username__icontains=username)
        if email:
            users = users.filter(email__icontains=email)
        return paginated_response(request, users, UserAdministrationSerializer)

    def post(self, request):
        serializer = UserAdministrationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def put(self, request, pk):
        user = get_object_or_404(self._user_queryset().select_for_update(of=("self",)), pk=pk)
        serializer = UserAdministrationSerializer(user, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def patch(self, request, pk):
        user = get_object_or_404(self._user_queryset().select_for_update(of=("self",)), pk=pk)
        serializer = UserAdministrationSerializer(user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def delete(self, request, pk):
        user = get_object_or_404(self._user_queryset().select_for_update(of=("self",)), pk=pk)
        if user.pk == request.user.pk or user.is_superuser:
            raise ValidationError({"detail": "You cannot delete yourself or a superuser."})
        if user.is_staff and not request.user.is_superuser:
            raise PermissionDenied("Only superusers can delete administrators.")
        user.delete()
        return Response("User deleted.", status=status.HTTP_204_NO_CONTENT)


class GroupView(APIView):
    permission_classes = [IsAuthenticated, GroupPermission]

    def _group_queryset(self):
        return Group.objects.prefetch_related("permissions__content_type")

    def get(self, request, pk=None):
        if pk:
            group = get_object_or_404(self._group_queryset(), pk=pk)
            return Response(GroupSerializer(group).data)

        groups = self._group_queryset().order_by("name")
        name = request.query_params.get("name")
        if name:
            groups = groups.filter(name__icontains=name)
        return paginated_response(request, groups, GroupSerializer)

    def post(self, request):
        serializer = GroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = serializer.save()
        return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)

    def patch(self, request, pk):
        group = get_object_or_404(self._group_queryset(), pk=pk)
        serializer = GroupSerializer(group, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        group = serializer.save()
        return Response(GroupSerializer(group).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        group = get_object_or_404(self._group_queryset(), pk=pk)
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


PUBLIC_ENDPOINTS = {
    "SessionView": "Public session bootstrap/login endpoint with explicit CSRF protection.",
    "PasswordResetRequestAPIView": "Public request endpoint; response does not reveal account existence.",
    "PasswordResetConfirmAPIView": "Public confirmation endpoint; uid and token prove reset authorization.",
    "InvitationInspectView": "Public token inspection; the high-entropy token proves access.",
    "InvitationAcceptView": "Public single-use account creation authorized by a locked invitation.",
}


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)

        return Response({"message": "Password is updated successfully."}, status=status.HTTP_200_OK)


class PermissionListView(APIView):
    permission_classes = [IsAuthenticated, UserPermission]

    def get(self, request):
        permissions = Permission.objects.select_related("content_type").order_by("content_type__app_label", "codename")
        return paginated_response(request, permissions, PermissionSerializer)


class UserPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserPreferencesSerializer(request.user.preferences)
        return Response(serializer.data)

    def put(self, request):
        serializer = UserPreferencesSerializer(request.user.preferences, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserPreferencesSerializer(request.user.preferences, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class ResetPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.preferences.reset_to_defaults()
        serializer = UserPreferencesSerializer(request.user.preferences)
        return Response({
            "message": "Preferences reset to defaults",
            "preferences": serializer.data,
        })


class ExtraSettingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, key):
        value = request.user.preferences.get_extra_setting(key)
        if value is None:
            return Response(
                {"error": f"Setting '{key}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({key: value})

    def post(self, request):
        key = request.data.get("key")
        value = request.data.get("value")

        if not key:
            return Response(
                {"error": "Key is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.preferences.set_extra_setting(key, value)
        return Response({
            "message": "Setting saved successfully",
            key: value,
        })

    def delete(self, request, key):
        preferences = request.user.preferences
        if key in preferences.extra_settings:
            del preferences.extra_settings[key]
            preferences.save(update_fields=["extra_settings", "updated_at"])
            return Response({"message": f"Setting '{key}' deleted"})
        return Response(
            {"error": f"Setting '{key}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


class PasswordResetRequestAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetAddressThrottle, PasswordResetAccountThrottle]

    def post(self, request):
        started_at = time.monotonic()
        try:
            serializer = PasswordResetRequestSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(
                {"detail": "If the email is registered, a link has been sent."},
                status=status.HTTP_200_OK,
            )
        finally:
            pad_password_reset_response(started_at)


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [
        PasswordResetConfirmAddressThrottle,
        PasswordResetCapabilityThrottle,
    ]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)
