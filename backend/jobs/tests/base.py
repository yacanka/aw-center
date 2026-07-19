import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class JobTestCase(TestCase):
    """Provide isolated artifact storage and authenticated job clients."""

    def setUp(self):
        """Create users, API client, and temporary media storage."""

        self.media_directory = Path(tempfile.mkdtemp())
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory / "public",
            PRIVATE_MEDIA_ROOT=self.media_directory / "private",
        )
        self.settings_override.enable()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="job-owner", password="test-password")
        self.other_user = user_model.objects.create_user(username="other-owner", password="test-password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        """Remove isolated artifact storage."""

        self.settings_override.disable()
        shutil.rmtree(self.media_directory, ignore_errors=True)

    def image_upload(self, name="sample.jpg"):
        """Return a minimally signature-valid JPEG upload."""

        return SimpleUploadedFile(name, b"\xff\xd8\xffmedia-payload", content_type="image/jpeg")
