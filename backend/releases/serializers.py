from rest_framework import serializers
from .models import ReleaseNote, ReleaseNoteItem


class ReleaseNoteIdField(serializers.IntegerField):
    """Accept JSON integer IDs without coercing booleans, floats or strings."""

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class BoundedReleaseNoteIdsField(serializers.ListField):
    """Reject oversized lists before validating and collecting child errors."""

    def run_child_validation(self, data):
        if self.max_length is not None and len(data) > self.max_length:
            self.fail("max_length", max_length=self.max_length)
        return super().run_child_validation(data)


class BulkSeenSerializer(serializers.Serializer):
    ids = BoundedReleaseNoteIdsField(
        child=ReleaseNoteIdField(min_value=1, max_value=9223372036854775807),
        max_length=1000,
        allow_empty=True,
        default=list,
    )


class ReleaseNoteItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReleaseNoteItem
        fields = ["id", "item_type", "heading", "body_md", "order"]


class ReleaseNoteSerializer(serializers.ModelSerializer):
    items = ReleaseNoteItemSerializer(many=True)

    class Meta:
        model = ReleaseNote
        fields = ["id", "version", "title", "published_at", "requires_ack", "items"]
