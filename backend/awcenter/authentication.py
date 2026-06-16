from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied


class CookieTokenAuthentication(TokenAuthentication):
    """Authenticate with a DRF token from a header or an HttpOnly cookie.

    Browser requests use the cookie-backed token strategy. Header token
    authentication stays available for non-browser clients and development
    fallback flows. Because browsers attach cookies automatically, unsafe
    cookie-authenticated requests must pass Django CSRF validation.
    """

    def authenticate(self, request):
        """Return authenticated credentials from header or CSRF-checked cookie."""
        header_authentication = super().authenticate(request)
        if header_authentication:
            return header_authentication

        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        if not raw_token:
            return None

        try:
            user_authentication = self.authenticate_credentials(raw_token)
        except AuthenticationFailed:
            return None

        self.enforce_csrf(request)
        return user_authentication

    def enforce_csrf(self, request):
        """Validate CSRF for unsafe cookie-authenticated browser requests."""
        csrf_check = CsrfViewMiddleware(lambda inner_request: None)
        csrf_check.process_request(request)
        reason = csrf_check.process_view(request, None, (), {})
        if reason:
            raise PermissionDenied(f"CSRF validation failed: {reason}")
