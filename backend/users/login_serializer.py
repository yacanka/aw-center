"""Authentication serializer with correct failure semantics."""

from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.exceptions import AuthenticationFailed, ValidationError


class LoginSerializer(AuthTokenSerializer):
    """Distinguish malformed login requests from rejected credentials."""

    def validate(self, attributes):
        """Return a 401 without revealing whether the username exists."""

        try:
            return super().validate(attributes)
        except ValidationError as error:
            raise AuthenticationFailed(
                "Invalid username or password.", code="AUTHENTICATION_FAILED"
            ) from error
