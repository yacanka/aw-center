from rest_framework import serializers
from .models import ReleaseNote, ReleaseNoteItem


class ReleaseNoteItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReleaseNoteItem
        fields = ["id", "item_type", "heading", "body_md", "order"]


class ReleaseNoteSerializer(serializers.ModelSerializer):
    items = ReleaseNoteItemSerializer(many=True)

    class Meta:
        model = ReleaseNote
        fields = ["id", "version", "title", "published_at", "requires_ack", "items"]