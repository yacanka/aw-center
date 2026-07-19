from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateJobStorage(FileSystemStorage):
    """Store job artifacts outside publicly served media roots."""

    @property
    def base_location(self):
        """Return the active environment-backed private root."""

        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        """Return an absolute private filesystem location."""

        return str(Path(self.base_location).resolve())

    @property
    def base_url(self):
        """Disable direct URLs so downloads must pass authorization."""

        return None


private_job_storage = PrivateJobStorage()
