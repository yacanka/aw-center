from rest_framework import serializers
from .models import Presentation, Slide

class SlideSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slide
        fields = ["id", "index", "image", "thumb", "updated_at"]

class PresentationSerializer(serializers.ModelSerializer):
    slides = SlideSerializer(many=True, read_only=True)

    class Meta:
        model = Presentation
        fields = ["id", "title", "file", "status", "created_at", "slides"]

class PresentationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Presentation
        fields = ["id", "title", "file"]