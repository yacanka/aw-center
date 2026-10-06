"""Strict browser conversation inputs; configuration remains server-owned."""
import re

from rest_framework import serializers

MAX_BODY_BYTES = 64 * 1024


class StrictTextField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        try:
            data.encode("utf-8")
        except UnicodeError:
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Unexpected fields."]})
        return super().to_internal_value(data)


class HistoryMessageSerializer(StrictSerializer):
    role = StrictTextField(max_length=9, trim_whitespace=False)
    content = StrictTextField(max_length=24000, trim_whitespace=False)

    def validate_role(self, value):
        if value not in ("user", "assistant"):
            raise serializers.ValidationError("A user or assistant role is required.")
        return value

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("A message is required.")
        return value


class AssistantRequestSerializer(StrictSerializer):
    message = StrictTextField(max_length=4000, trim_whitespace=False)
    history = HistoryMessageSerializer(many=True, max_length=12, default=list)
    current_path = StrictTextField(max_length=200, allow_blank=True, default="", trim_whitespace=False)

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("A message is required.")
        return value

    def validate_history(self, value):
        if sum(len(row["content"]) for row in value) > 24000:
            raise serializers.ValidationError("Conversation history is too long.")
        return value

    def validate_current_path(self, value):
        # URL state can contain private filters; only the router path enters context.
        path = re.split(r"[?#]", value, maxsplit=1)[0]
        if path and (not re.fullmatch(r"/[A-Za-z0-9/_-]*", path) or "//" in path):
            raise serializers.ValidationError("A router-relative path is required.")
        return path
