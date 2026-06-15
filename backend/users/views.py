from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.models import Permission, update_last_login
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import UserPermission
from common.views import paginated_response
from .serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PermissionSerializer,
    UserPreferencesSerializer,
    UserSerializer,
)

User = get_user_model()


class UserView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated(), UserPermission()]

    def _user_queryset(self):
        return User.objects.select_related("preferences").prefetch_related(
            "user_permissions__content_type",
            "groups",
        )

    def get(self, request, pk=None):
        if pk:
            user = get_object_or_404(self._user_queryset(), pk=pk)
            serializer = UserSerializer(user, context={"request": request})
            return Response(serializer.data)

        users = self._user_queryset().order_by("id")
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
        return paginated_response(request, users, UserSerializer)

    def post(self, request):
        serializer = UserSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        user = get_object_or_404(self._user_queryset(), pk=pk)
        serializer = UserSerializer(user, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        user = get_object_or_404(self._user_queryset(), pk=pk)
        serializer = UserSerializer(user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        user = get_object_or_404(self._user_queryset(), pk=pk)
        user.delete()
        return Response("User deleted.", status=status.HTTP_204_NO_CONTENT)


class CustomAuthToken(ObtainAuthToken):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        update_last_login(None, user)
        response = Response(
            {
                "detail": "Login successful.",
                "user": UserSerializer(user, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )
        response.set_cookie(
            settings.AUTH_COOKIE_NAME,
            token.key,
            httponly=True,
            samesite=settings.AUTH_COOKIE_SAMESITE,
            secure=settings.AUTH_COOKIE_SECURE,
            max_age=settings.AUTH_COOKIE_MAX_AGE,
        )
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
        except Token.DoesNotExist:
            pass
        response = Response("Logout successful.", status=status.HTTP_200_OK)
        response.delete_cookie(settings.AUTH_COOKIE_NAME)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


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


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


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

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "If the email is registered, a link has been sent."}, status=status.HTTP_200_OK)


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)
