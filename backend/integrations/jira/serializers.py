from rest_framework import serializers


class JiraSessionConnectSerializer(serializers.Serializer):
    """Accept an opaque JIRA credential only at the canonical session resource."""

    JSESSIONID = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=4096,
        trim_whitespace=True,
    )

    def validate_JSESSIONID(self, value):
        if any(character.isspace() for character in value):
            raise serializers.ValidationError("Enter a valid JIRA session credential.")
        return value
