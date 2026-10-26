"""Slide writes must not restore deleted rows or orphan replaced images."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import Presentation, Slide
from .tests import _png_bytes
from .views import SlideViewSet


class SlideWriteConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.private_root = Path(self.directory.name)
        settings = override_settings(PRIVATE_MEDIA_ROOT=self.private_root)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = get_user_model().objects.create_user("slide-concurrent")
        self.presentation = Presentation.objects.create(owner=self.user, title="Synthetic")
        payload = _png_bytes()
        self.slide = Slide.objects.create(
            presentation=self.presentation, index=1,
            image=ContentFile(payload, name="slide.png"),
            thumb=ContentFile(payload, name="thumb.png"),
            image_sha256=hashlib.sha256(payload).hexdigest(),
            thumb_sha256=hashlib.sha256(payload).hexdigest(),
        )
        self.url = f"/api/tools/presentations/slides/{self.slide.pk}/"

    def replace_slide(self, name):
        try:
            client = APIClient()
            client.force_authenticate(self.user)
            return client.patch(self.url, {
                "image": SimpleUploadedFile(name, _png_bytes(), content_type="image/png"),
            }, format="multipart")
        finally:
            connections.close_all()

    def stored_files(self):
        return {str(path.relative_to(self.private_root))
                for path in self.private_root.rglob("*") if path.is_file()}

    def test_overlapping_replacements_remove_intermediate_files(self):
        ready = Barrier(2)
        first_saved = Event()
        payload = _png_bytes("red")

        def normalize(upload):
            ready.wait(timeout=10)
            if upload.name == "second.png":
                self.assertTrue(first_saved.wait(timeout=10))
            return payload, payload

        def first_replace():
            try:
                return self.replace_slide("first.png")
            finally:
                first_saved.set()

        with patch("pptxgallery.views.normalized_slide_payloads", side_effect=normalize):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(first_replace)
                second = pool.submit(self.replace_slide, "second.png")
                self.assertEqual(first.result(timeout=30).status_code, 200)
                self.assertEqual(second.result(timeout=30).status_code, 200)
        self.slide.refresh_from_db()
        self.assertEqual(self.stored_files(), {self.slide.image.name, self.slide.thumb.name})

    def test_delete_during_normalization_cannot_resurrect_slide(self):
        payload = _png_bytes("red")

        def delete_slide():
            try:
                Slide.objects.get(pk=self.slide.pk).delete()
            finally:
                connections.close_all()

        def normalize(_upload):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(delete_slide).result(timeout=10)
            return payload, payload

        with patch("pptxgallery.views.normalized_slide_payloads", side_effect=normalize):
            response = self.replace_slide("replacement.png")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Slide.objects.filter(pk=self.slide.pk).exists())
        self.assertEqual(self.stored_files(), set())

    def test_delete_from_stale_snapshot_removes_current_images(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(self.replace_slide, "replacement.png").result(timeout=30)
        self.assertEqual(response.status_code, 200)
        view = SlideViewSet()
        view.request = SimpleNamespace(user=self.user)
        view.perform_destroy(self.slide)
        self.assertFalse(Slide.objects.filter(pk=self.slide.pk).exists())
        self.assertEqual(self.stored_files(), set())

    def test_failed_row_save_preserves_old_files_and_removes_new_files(self):
        original_files = self.stored_files()
        with patch.object(Slide, "save", side_effect=RuntimeError("Synthetic write failure")):
            response = self.replace_slide("replacement.png")
        self.assertEqual(response.status_code, 500)
        self.slide.refresh_from_db()
        self.assertEqual(self.stored_files(), original_files)
        self.assertEqual(original_files, {self.slide.image.name, self.slide.thumb.name})
