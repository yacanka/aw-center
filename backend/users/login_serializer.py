"""Credential validation for the browser-only Django session endpoint."""

from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
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
