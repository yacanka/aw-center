"""Streaming upload guards that stop oversized bodies before disk exhaustion."""

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class AbsoluteUploadLimitHandler(FileUploadHandler):
    """Abort a file stream after the deployment-wide absolute byte limit."""

    def __init__(self, request=None):
        """Initialize counters for the active multipart request."""

        super().__init__(request)
        self.received_bytes = 0

    def new_file(self, *args, **kwargs):
        """Reset the per-file counter when a multipart file starts."""

        super().new_file(*args, **kwargs)
        self.received_bytes = 0

    def receive_data_chunk(self, raw_data, start):
        """Pass safe chunks onward and stop an oversized upload immediately."""

        self.received_bytes += len(raw_data)
        if self.received_bytes > self.maximum_bytes:
            self.request.upload_limit_exceeded = True
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        """Let Django's memory or temporary-file handler build the file object."""

        return None

    @property
    def maximum_bytes(self) -> int:
        """Return the absolute upload ceiling configured for this deployment."""

        return int(getattr(settings, "AWCENTER_ABSOLUTE_MAX_UPLOAD_BYTES", 600 * 1024 * 1024))
