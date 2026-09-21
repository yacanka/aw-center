"""Credential validation for the browser-only Django session endpoint."""

from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from .username_policy import validate_username_format


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        min_length=6, max_length=6, trim_whitespace=True,
        validators=[validate_username_format],
    )
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate(self, attributes):
        user = authenticate(
            request=self.context.get("request"),
            username=attributes["username"],
            password=attributes["password"],
        )
        if user is None or not user.is_active:
            raise AuthenticationFailed(
                "Invalid username or password.",
                code="AUTHENTICATION_FAILED",
            )
        attributes["user"] = user
        return attributes
