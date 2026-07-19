from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from .models import Presentation, Slide
from .serializers import PresentationSerializer, PresentationCreateSerializer, SlideSerializer
from .converters import convert_pptx_to_images
from awcenter.file_security import (
    IMAGE_POLICY,
    PRESENTATION_POLICY,
    validate_request_upload,
    validate_uploaded_file,
)

class PresentationViewSet(viewsets.ModelViewSet):
    queryset = Presentation.objects.all().order_by("-created_at")
    serializer_class = PresentationSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        """Create and convert a presentation through the validated upload flow."""

        return self.upload(request)

    def get_serializer_class(self):
        if self.action in ["create", "upload"]:
            return PresentationCreateSerializer
        return PresentationSerializer

    @action(detail=False, methods=["post"])
    def upload(self, request):
        validate_request_upload(request, "file", PRESENTATION_POLICY)
        ser = PresentationCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pres = ser.save(status="pending")
        # Senkron dönüşüm (küçük dosyalar için); büyükler için Celery önerilir
        convert_pptx_to_images(pres)
        return Response(PresentationSerializer(pres, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="reconvert")
    def reconvert(self, request, pk=None):
        pres = self.get_object()
        convert_pptx_to_images(pres)
        return Response(PresentationSerializer(pres, context={"request": request}).data)

class SlideViewSet(viewsets.ModelViewSet):
    queryset = Slide.objects.select_related("presentation").all()
    serializer_class = SlideSerializer

    def update(self, request, *args, **kwargs):
        # Görsel güncelleme (yeni image dosyası gönder)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        file_obj = request.FILES.get("image")
        if file_obj:
            validate_uploaded_file(file_obj, IMAGE_POLICY)
            instance.image.save(file_obj.name, file_obj, save=True)
        if partial:
            return Response(SlideSerializer(instance, context={"request": request}).data)
        return super().update(request, *args, **kwargs)
