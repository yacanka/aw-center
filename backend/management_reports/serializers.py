from rest_framework import serializers

from projects.registry import get_project_definitions_by_capability


class CaptureSerializer(serializers.Serializer):
    project_slugs = serializers.ListField(
        child=serializers.SlugField(max_length=64), allow_empty=False,
        max_length=len(get_project_definitions_by_capability("compliance")),
    )
    title = serializers.CharField(max_length=120, trim_whitespace=True)
    management_note = serializers.CharField(max_length=2000, allow_blank=True, default="", trim_whitespace=False)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({"detail": "Only project_slugs, title and management_note may be submitted."})
        return super().to_internal_value(data)
