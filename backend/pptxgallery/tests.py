import hashlib
from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from awcenter.job_executors import resolve_job_executor
from jobs.models import JobStatus
from jobs.services import create_job
from jobs.tests.base import JobTestCase
from jobs.worker import claim_next_job, execute_claimed_job
from pptxgallery.models import Presentation, Slide


def _presentation_upload(name="presentation.pptx"):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        marker = ZipInfo("ppt/presentation.xml", date_time=(1980, 1, 1, 0, 0, 0))
        marker.compress_type = ZIP_DEFLATED
        archive.writestr(marker, "<p:presentation/>")
    return SimpleUploadedFile(
        name,
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


def _png_bytes(color="blue"):
    output = BytesIO()
    Image.new("RGB", (64, 48), color).save(output, format="PNG")
    return output.getvalue()


class PresentationApiTests(JobTestCase):
    def test_upload_is_private_durable_and_idempotent(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "presentation-upload-1"}
        first = self.client.post(
            "/api/tools/presentations/presentations/upload/",
            {"title": "Architecture", "file": _presentation_upload()},
            format="multipart",
            **headers,
        )
        replay = self.client.post(
            "/api/tools/presentations/presentations/upload/",
            {"title": "Architecture", "file": _presentation_upload()},
            format="multipart",
            **headers,
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(Presentation.objects.count(), 1)
        presentation = Presentation.objects.get()
        self.assertTrue(presentation.file.name.startswith(f"presentations/{self.user.id}/"))
        self.assertIsNone(presentation.file.storage.base_url)

    def test_list_is_paginated_and_owner_scoped(self):
        self._create_presentation(self.user, "Owned")
        other = self._create_presentation(self.other_user, "Other")

        response = self.client.get("/api/tools/presentations/presentations/")
        inaccessible = self.client.get(
            f"/api/tools/presentations/presentations/{other.id}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(inaccessible.status_code, 404)

    def test_slide_download_verifies_owner_and_digest(self):
        presentation = self._create_presentation(self.user, "Owned")
        payload = _png_bytes()
        slide = Slide.objects.create(
            presentation=presentation,
            index=1,
            image=ContentFile(payload, name="slide.png"),
            image_sha256=hashlib.sha256(payload).hexdigest(),
        )

        response = self.client.get(f"/api/tools/presentations/slides/{slide.id}/image/")
        slide.image_sha256 = hashlib.sha256(b"different").hexdigest()
        slide.save(update_fields=["image_sha256"])
        tampered = self.client.get(f"/api/tools/presentations/slides/{slide.id}/image/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(tampered.status_code, 409)
        self.assertEqual(tampered.data["code"], "SLIDE_INTEGRITY_FAILED")

    def _create_presentation(self, owner, title):
        upload = _presentation_upload()
        digest = hashlib.sha256(upload.read()).hexdigest()
        upload.seek(0)
        presentation = Presentation.objects.create(
            owner=owner,
            title=title,
            source_name=upload.name,
            source_sha256=digest,
        )
        presentation.file.save(upload.name, upload, save=True)
        return presentation


class PresentationJobTests(JobTestCase):
    @patch("pptxgallery.job_executor.render_pptx_to_images")
    def test_executor_publishes_fenced_private_slides(self, render):
        upload = _presentation_upload()
        digest = hashlib.sha256(upload.read()).hexdigest()
        upload.seek(0)
        presentation = Presentation.objects.create(
            owner=self.user,
            title="Durable",
            source_name=upload.name,
            source_sha256=digest,
        )
        presentation.file.save(upload.name, upload, save=True)
        upload.seek(0)
        job, _ = create_job(
            self.user,
            "presentations.convert",
            "Convert Durable",
            {"presentation_id": str(presentation.id), "title": presentation.title},
            upload,
        )
        presentation.conversion_job = job
        presentation.save(update_fields=["conversion_job"])

        def render_slide(_source, work_directory):
            image_path = work_directory / "slide-1.png"
            image_path.write_bytes(_png_bytes())
            return [image_path]

        render.side_effect = render_slide
        claimed = claim_next_job("presentation-worker")
        execute_claimed_job(claimed, resolve_job_executor)

        job.refresh_from_db()
        presentation.refresh_from_db()
        slide = presentation.slides.get()
        self.assertEqual(job.status, JobStatus.SUCCEEDED)
        self.assertEqual(job.result_summary["presentation_id"], str(presentation.id))
        self.assertEqual(presentation.status, "ready")
        self.assertTrue(slide.image.storage.exists(slide.image.name))
        self.assertEqual(len(slide.image_sha256), 64)
