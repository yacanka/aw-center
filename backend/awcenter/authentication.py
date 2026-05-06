from rest_framework.authentication import TokenAuthentication


class CookieTokenAuthentication(TokenAuthentication):
    """Authenticate using DRF token from Authorization header or HttpOnly cookie."""

    cookie_name = "auth_token"

    def authenticate(self, request):
        header_auth = super().authenticate(request)
        if header_auth:
            return header_auth

        raw_token = request.COOKIES.get(self.cookie_name)
        if not raw_token:
            return None

        return self.authenticate_credentials(raw_token)
