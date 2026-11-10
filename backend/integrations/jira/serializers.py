from rest_framework import serializers

from .client import validated_personal_access_token


class JiraSessionConnectSerializer(serializers.Serializer):
    """Accept an opaque JIRA credential only at the canonical session resource."""

    JSESSIONID = serializers.CharField(
        required=False,
        write_only=True,
        min_length=8,
        max_length=4096,
        trim_whitespace=True,
    )
    personal_access_token = serializers.CharField(
        required=False,
        write_only=True,
        min_length=8,
        max_length=4096,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        if ("JSESSIONID" in attrs) == ("personal_access_token" in attrs):
            raise serializers.ValidationError("Provide exactly one JIRA credential.")
        return attrs

    def validate_personal_access_token(self, value):
        try:
            return validated_personal_access_token(value)
        except ValueError:
            raise serializers.ValidationError("Enter a valid JIRA personal access token.") from None

    def validate_JSESSIONID(self, value):
        if any(character.isspace() for character in value):
            raise serializers.ValidationError("Enter a valid JIRA session credential.")
        return value
