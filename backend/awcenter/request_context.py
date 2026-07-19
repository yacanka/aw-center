"""Request correlation utilities for API responses and application logs."""

import contextvars
import re
import uuid


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_request_id = contextvars.ContextVar("request_id", default="-")


def get_request_id():
    """Return the active request identifier or a log-safe placeholder."""

    return _request_id.get()


def create_request_id(candidate=None):
    """Return a validated caller identifier or generate an opaque one."""

    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class RequestCorrelationMiddleware:
    """Attach one safe correlation identifier to each request and response."""

    def __init__(self, get_response):
        """Store the downstream Django response callable."""

        self.get_response = get_response

    def __call__(self, request):
        """Set request context, invoke the application, and clear context."""

        request_id = create_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.request_id = request_id
        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            _request_id.reset(token)


class RequestIdLogFilter:
    """Add the active request identifier to every formatted log record."""

    def filter(self, record):
        """Enrich the record and always allow it to be emitted."""

        request = getattr(record, "request", None)
        record.request_id = getattr(request, "request_id", get_request_id())
        return True
