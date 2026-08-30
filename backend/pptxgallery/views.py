"""Owner-scoped presentation gallery and durable conversion endpoints."""

import hashlib
from pathlib import Path

from django.core.files import File
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from awcenter.api_errors import error_response
from awcenter.file_security import (
    IMAGE_POLICY,
    PRESENTATION_POLICY,
    validate_request_upload,
    validate_uploaded_file,
)
from awcenter.private_files import PrivateFileIntegrityError, open_verified_private_file
from jobs.api import job_creation_response
from jobs.models import JobStatus
from jobs.persistence import IdempotencyConflict, find_idempotent_job
from jobs.services import create_job

from .converters import normalized_slide_payloads
from .models import Presentation, Slide
from .serializers import PresentationSerializer, PresentationUploadSerializer, SlideSerializer

ACTIVE_JOB_STATUSES = {
    JobStatus.AWAITING_CONFIRMATION,
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
}


class PresentationViewSet(ModelViewSet):
    serializer_class = PresentationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return (
            Presentation.objects.filter(owner=self.request.user)
            .select_related("conversion_job")
            .prefetch_related("slides")
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        return self.upload(request)

    @action(detail=False, methods=["post"])
    def upload(self, request):
        upload = validate_request_upload(request, "file", PRESENTATION_POLICY)
        serializer = PresentationUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        title = serializer.validated_title()
        idempotency_key = _required_idempotency_key(request)
        existing = find_idempotent_job(request.user, "presentations.convert", idempotency_key)
        if existing:
            presentation = get_object_or_404(
                self.get_queryset(),
                pk=existing.parameters.get("presentation_id"),
            )
            if presentation.title != title:
                raise IdempotencyConflict()
            replay, created = create_job(
                request.user,
                "presentations.convert",
                f"Convert {title}",
                existing.parameters,
                upload,
                idempotency_key=idempotency_key,
                request_id=getattr(request, "request_id", ""),
            )
            return job_creation_response(replay, created)

        presentation = Presentation(
            owner=request.user,
            title=title,
            source_name=Path(upload.name).name[:180],
            source_sha256=_upload_digest(upload),
        )
        presentation.save()
        try:
            presentation.file.save(upload.name, upload, save=True)
            upload.seek(0)
            job, created = create_job(
                request.user,
                "presentations.convert",
                f"Convert {title}",
                {"presentation_id": str(presentation.id), "title": title},
                upload,
                idempotency_key=idempotency_key,
                request_id=getattr(request, "request_id", ""),
            )
            presentation.conversion_job = job
            presentation.save(update_fields=["conversion_job"])
        except Exception:
            presentation.delete()
            raise
        return job_creation_response(job, created)

    @action(detail=True, methods=["post"], url_path="reconvert")
    def reconvert(self, request, pk=None):
        presentation = self.get_object()
        if presentation.conversion_job and presentation.conversion_job.status in ACTIVE_JOB_STATUSES:
            return error_response(
                "Presentation conversion is already active.",
                "PRESENTATION_JOB_ACTIVE",
                response_status=409,
            )
        idempotency_key = _required_idempotency_key(request)
        try:
            source = open_verified_private_file(
                presentation.file,
                presentation.source_sha256,
            )
        except (OSError, PrivateFileIntegrityError):
            return error_response(
                "Presentation source failed integrity verification.",
                "PRESENTATION_SOURCE_INTEGRITY_FAILED",
                response_status=409,
            )
        try:
            job, created = create_job(
                request.user,
                "presentations.convert",
                f"Convert {presentation.title}",
                {"presentation_id": str(presentation.id), "title": presentation.title},
                File(source, name=presentation.source_name),
                idempotency_key=idempotency_key,
                request_id=getattr(request, "request_id", ""),
            )
        finally:
            source.close()
        presentation.conversion_job = job
        presentation.status = "pending"
        presentation.save(update_fields=["conversion_job", "status"])
        return job_creation_response(job, created)

    def perform_destroy(self, instance):
        instance.delete()


class SlideViewSet(ModelViewSet):
    serializer_class = SlideSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Slide.objects.filter(presentation__owner=self.request.user).select_related(
            "presentation"
        )

    def partial_update(self, request, *args, **kwargs):
        slide = self.get_object()
        upload = validate_request_upload(request, "image", IMAGE_POLICY)
        validate_uploaded_file(upload, IMAGE_POLICY)
        image_bytes, thumb_bytes = normalized_slide_payloads(upload)
        old_names = [slide.image.name, slide.thumb.name]
        slide.image.save("slide.png", ContentFile(image_bytes), save=False)
        slide.thumb.save("thumb.png", ContentFile(thumb_bytes), save=False)
        slide.image_sha256 = hashlib.sha256(image_bytes).hexdigest()
        slide.thumb_sha256 = hashlib.sha256(thumb_bytes).hexdigest()
        slide.save()
        _delete_names(name for name in old_names if name not in {slide.image.name, slide.thumb.name})
        return self.retrieve(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=True, methods=["get"])
    def image(self, request, pk=None):
        slide = self.get_object()
        return _private_image_response(slide.image, slide.image_sha256, f"slide-{slide.index}.png")

    @action(detail=True, methods=["get"])
    def thumb(self, request, pk=None):
        slide = self.get_object()
        if not slide.thumb:
            return error_response(
                "Slide thumbnail is unavailable.",
                "SLIDE_THUMB_MISSING",
                response_status=404,
            )
        return _private_image_response(
            slide.thumb,
            slide.thumb_sha256,
            f"slide-{slide.index}-thumb.png",
        )


def _required_idempotency_key(request):
    key = str(request.headers.get("Idempotency-Key", "")).strip()
    if not key:
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"idempotency_key": "Idempotency-Key is required."})
    return key


def _upload_digest(upload):
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def _private_image_response(field_file, expected_sha256, filename):
    try:
        source = open_verified_private_file(field_file, expected_sha256)
    except (OSError, PrivateFileIntegrityError):
        return error_response(
            "Slide image failed integrity verification.",
            "SLIDE_INTEGRITY_FAILED",
            response_status=409,
        )
    return FileResponse(source, filename=filename, content_type="image/png")


def _delete_names(names):
    storage = Presentation._meta.get_field("file").storage
    for name in names:
        if name:
            storage.delete(name)
