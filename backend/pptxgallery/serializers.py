from pathlib import Path

from django.urls import reverse
from rest_framework import serializers

from jobs.models import JobStatus
from .models import Presentation, Slide


class SlideSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = Slide
        fields = ["id", "index", "image_url", "thumb_url", "updated_at"]

    def get_image_url(self, slide):
        return reverse("slides-image", kwargs={"pk": slide.pk})

    def get_thumb_url(self, slide):
        if not slide.thumb:
            return None
        return reverse("slides-thumb", kwargs={"pk": slide.pk})


class PresentationSerializer(serializers.ModelSerializer):
    slides = serializers.SerializerMethodField()
    conversion_job_id = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Presentation
        fields = [
            "id",
            "title",
            "status",
            "created_at",
            "conversion_job_id",
            "slides",
        ]

    def get_conversion_job_id(self, presentation):
        return str(presentation.conversion_job_id) if presentation.conversion_job_id else None

    def get_status(self, presentation):
        job = presentation.conversion_job
        if job is None:
            return presentation.status
        if job.status in {JobStatus.QUEUED, JobStatus.AWAITING_CONFIRMATION}:
            return "pending"
        if job.status in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
            return "converting"
        if job.status == JobStatus.SUCCEEDED:
            return "ready"
        return "failed"

    def get_slides(self, presentation):
        if self.get_status(presentation) != "ready":
            return []
        return SlideSerializer(presentation.slides.all(), many=True).data


class PresentationUploadSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    file = serializers.FileField()

    def validated_title(self):
        title = self.validated_data.get("title", "").strip()
        if title:
            return title
        return Path(self.validated_data["file"].name).stem[:255] or "Presentation"
