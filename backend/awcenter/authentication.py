from django.conf import settings
from rest_framework.authentication import TokenAuthentication


class CookieTokenAuthentication(TokenAuthentication):
    """Authenticate using DRF token from Authorization header or HttpOnly cookie."""

    def authenticate(self, request):
        header_auth = super().authenticate(request)
        if header_auth:
            return header_auth

        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        if not raw_token:
            return None

        return self.authenticate_credentials(raw_token)
