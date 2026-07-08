import logging

from django.utils.deprecation import MiddlewareMixin

request_logger = logging.getLogger("awcenter.requests")


class RequestUserLogMiddleware(MiddlewareMixin):
    """Log authenticated request metadata without writing sensitive payloads."""

    def process_request(self, request):
        """Emit one request log line for production request tracing."""
        username = self.get_username(request)
        ip = self.get_client_ip(request)
        method = request.method
        path = request.path
        request_logger.info("%s - %s: %s %s", ip, username, method, path)
        return None

    def get_username(self, request):
        """Return authenticated username or an anonymous placeholder."""
        if request.user and request.user.is_authenticated:
            return request.user.username
        return "Anonymous"

    def get_client_ip(self, request):
        """Return the closest client IP from proxy headers or REMOTE_ADDR."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
