"""Fence development HTTP writes that can change reset-owned records."""

from django.http import JsonResponse

from compliance.reset_guard import ResetInProgress, lock_reset_state, reset_enabled


class DeveloperResetWriteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        affected = (
            path.startswith("/api/projects/")
            or path.startswith("/admin/compliance/")
            or path.startswith("/admin/orgs/")
        )
        if not reset_enabled() or not affected or request.method in {"GET", "HEAD", "OPTIONS"}:
            return self.get_response(request)
        with lock_reset_state() as state:
            if state.active:
                return JsonResponse({
                    "detail": ResetInProgress.default_detail,
                    "code": ResetInProgress.default_code,
                    "request_id": getattr(request, "request_id", ""),
                }, status=409)
            return self.get_response(request)
