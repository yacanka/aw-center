"""Shared API error contract utilities for AW Center."""

from http import HTTPStatus

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

DEFAULT_ERROR_CODE = "ERROR"
VALIDATION_ERROR_CODE = "VALIDATION_ERROR"


class ErrorCodes:
    """Machine-readable API error codes used by new endpoints."""

    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    ERROR = DEFAULT_ERROR_CODE
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    PARSE_ERROR = "PARSE_ERROR"
    THROTTLED = "THROTTLED"
    VALIDATION_ERROR = VALIDATION_ERROR_CODE


class ApiErrorContractMiddleware:
    """Normalize manual DRF error responses to the shared API error contract."""

    def __init__(self, get_response):
        """Store the downstream Django response callable."""

        self.get_response = get_response

    def __call__(self, request):
        """Return the downstream response without changing non-template responses."""

        return self.get_response(request)

    def process_template_response(self, request, response):
        """Normalize unrendered DRF error responses before rendering."""

        return normalize_error_response(response)


_STATUS_CODE_MAP = {
    status.HTTP_400_BAD_REQUEST: VALIDATION_ERROR_CODE,
    status.HTTP_401_UNAUTHORIZED: ErrorCodes.AUTHENTICATION_FAILED,
    status.HTTP_403_FORBIDDEN: ErrorCodes.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCodes.NOT_FOUND,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCodes.THROTTLED,
}


def api_exception_handler(exception, context):
    """Convert DRF exceptions to the standard AW Center error contract."""

    response = exception_handler(exception, context)
    if response is None:
        return None

    response.data = build_error_payload(response.data, response.status_code, exception)
    return response


def error_response(detail, code=DEFAULT_ERROR_CODE, errors=None, response_status=400):
    """Return an error response that follows the shared API error contract."""

    payload = build_error_payload({"detail": detail}, response_status, code=code)
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=response_status)


def build_error_payload(data, status_code, exception=None, code=None):
    """Build a serializable API error payload with detail, code, and optional errors."""

    errors = _extract_errors(data)
    detail = _extract_detail(data) or _default_detail(status_code)
    error_code = code or _extract_code(data) or _exception_code(exception)
    payload = {"detail": str(detail), "code": _normalize_code(error_code, status_code)}
    if errors is not None:
        payload["errors"] = errors
    return payload


def normalize_error_response(response):
    """Normalize manual DRF error responses when they use legacy payloads."""

    if not _should_normalize_response(response):
        return response

    response.data = build_error_payload(response.data, response.status_code)
    return response


def _should_normalize_response(response):
    if not isinstance(response, Response):
        return False
    if response.status_code < status.HTTP_400_BAD_REQUEST:
        return False
    return not _is_standard_error_payload(response.data)


def _is_standard_error_payload(data):
    if not isinstance(data, dict):
        return False
    return isinstance(data.get("detail"), str) and isinstance(data.get("code"), str)


def _extract_detail(data):
    if isinstance(data, dict):
        return data.get("detail") or data.get("message") or data.get("error")
    if isinstance(data, list):
        return _join_values(data)
    return data


def _extract_errors(data):
    if not isinstance(data, dict):
        return None
    if "errors" in data:
        return data["errors"]
    return _validation_errors(data)


def _validation_errors(data):
    non_error_keys = {"detail", "message", "error", "code"}
    errors = {key: value for key, value in data.items() if key not in non_error_keys}
    return errors or None


def _extract_code(data):
    if isinstance(data, dict) and isinstance(data.get("code"), str):
        return data["code"]
    return None


def _exception_code(exception):
    if exception is None or not hasattr(exception, "get_codes"):
        return None
    codes = exception.get_codes()
    return codes if isinstance(codes, str) else None


def _normalize_code(code, status_code):
    if isinstance(code, str) and code:
        return code.upper()
    return _STATUS_CODE_MAP.get(status_code, DEFAULT_ERROR_CODE)


def _default_detail(status_code):
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed."


def _join_values(values):
    return " ".join(str(value) for value in values if value)
