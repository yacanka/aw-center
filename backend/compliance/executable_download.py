"""Project-authorized distribution of the configured dashboard executable."""

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import StreamingHttpResponse

from awcenter.api_errors import error_response
from .executable_config import database_path_trailer, permitted_share, template_size, validate_database_path


class ExecutableResponse(StreamingHttpResponse):
    """Stream the same open template and a request-local trailer under WSGI or ASGI."""

    def __init__(self, template, size, trailer, *, asynchronous):
        self.template = template
        self.trailer = trailer
        super().__init__(
            self._async_chunks() if asynchronous else self._chunks(),
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": 'attachment; filename="CertificationDashboard.exe"',
                "Content-Length": str(size + len(trailer)),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def _chunks(self):
        yield from iter(lambda: self.template.read(256 * 1024), b"")
        yield self.trailer

    async def _async_chunks(self):
        read = sync_to_async(self.template.read, thread_sensitive=False)
        while chunk := await read(256 * 1024):
            yield chunk
        yield self.trailer

    def close(self):
        try:
            self.template.close()
        finally:
            super().close()


def download_executable(request):
    value = request.data.get("database_path") if isinstance(request.data, dict) else None
    try:
        path = validate_database_path(value)
    except ValueError as exc:
        return error_response(str(exc), "INVALID_DATABASE_PATH")
    trusted = path.startswith("\\\\") and permitted_share(path, settings.AWCENTER_DASHBOARD_SHARES)
    trailer = database_path_trailer(path, auto_open_network=trusted)
    try:
        template = settings.DASHBOARD_EXECUTABLE_TEMPLATE.open("rb")
        try:
            size = template_size(template)
            return ExecutableResponse(template, size, trailer, asynchronous=hasattr(request, "scope"))
        except BaseException:
            template.close()
            raise
    except (OSError, ValueError):
        return error_response(
            "Windows okuyucu paketi henüz kullanıma hazır değil. Yöneticinize başvurun.",
            "DASHBOARD_EXECUTABLE_UNAVAILABLE", response_status=503,
        )
