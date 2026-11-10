import logging
import time

request_logger = logging.getLogger("awcenter.requests")


class RequestUserLogMiddleware:
    """Emit one payload-free structured event after every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - started_at) * 1000, 2)
        user = getattr(request, "user", None)
        user_id = user.pk if user is not None and user.is_authenticated else None
        request_logger.info(
            "request.completed",
            extra={
                "event": "request.completed",
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
            },
        )
        return response
