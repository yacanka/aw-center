"""Browser-only Django session resource with explicit CSRF protection."""

from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie

from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.jira.sessions import clear_jira_session

from .login_serializer import LoginSerializer
from .throttles import LoginAccountThrottle, LoginAddressThrottle


def session_user_payload(user):
    return {
        "id": user.pk,
        "username": user.get_username(),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "permissions": sorted(user.get_all_permissions()),
    }


class SessionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def get_throttles(self):
        """Throttle credential validation without slowing session bootstrap/logout."""

        if self.request.method == "POST":
            return [LoginAddressThrottle(), LoginAccountThrottle()]
        return []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"state": "anonymous", "user": None})
        return Response(
            {"state": "authenticated", "user": session_user_payload(request.user)}
        )

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        login(request, serializer.validated_data["user"])
        return Response(
            {
                "state": "authenticated",
                "user": session_user_payload(serializer.validated_data["user"]),
            }
        )

    @method_decorator(csrf_protect)
    def delete(self, request):
        if not request.user.is_authenticated:
            return Response({"state": "anonymous", "user": None})
        clear_jira_session(request.user)
        logout(request)
        return Response(status=204)
