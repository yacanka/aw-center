from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers

from .invitation_management import invitation_status
from .invitation_service import inspect_invitation
from .models import UserInvitation

User = get_user_model()


class InvitationCreateSerializer(serializers.Serializer):
    """Validate administrator-controlled invitation properties."""

    email = serializers.EmailField(max_length=254)
    group_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
        max_length=50,
    )

    def validate_email(self, value):
        """Normalize email casing before persistence and comparison."""

        return value.strip().casefold()


class InvitationQuerySerializer(serializers.Serializer):
    """Validate bounded invitation audit filters."""

    search = serializers.CharField(required=False, allow_blank=True, max_length=254)
    status = serializers.ChoiceField(
        required=False, choices=("active", "used", "expired", "revoked")
    )


class InvitationListSerializer(serializers.ModelSerializer):
    """Expose invitation lifecycle metadata without secret token digests."""

    created_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    used_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    groups = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    status = serializers.SerializerMethodField()

    class Meta:
        model = UserInvitation
        fields = (
            "id",
            "email",
            "groups",
            "status",
            "created_by",
            "created_at",
            "expires_at",
            "used_by",
            "used_at",
            "revoked_at",
        )

    def get_status(self, invitation):
        """Return the current lifecycle state at serialization time."""

        return invitation_status(invitation)


class InvitationTokenSerializer(serializers.Serializer):
    """Validate the bounded raw token request envelope."""

    token = serializers.CharField(min_length=40, max_length=100, trim_whitespace=False)


class InvitationAcceptSerializer(InvitationTokenSerializer):
    """Validate self-registration fields authorized by an invitation token."""

    username = serializers.CharField(
        min_length=3,
        max_length=150,
        validators=[UnicodeUsernameValidator()],
    )
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    password_confirm = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )

    def validate_username(self, value):
        """Prevent confusing case-only username duplicates."""

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already in use.")
        return value

    def validate(self, attrs):
        """Validate token state, matching passwords, and Django password policy."""

        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        invitation = inspect_invitation(attrs["token"])
        candidate = User(
            username=attrs["username"],
            email=invitation.email,
            first_name=attrs["first_name"],
            last_name=attrs["last_name"],
        )
        validate_password(attrs["password"], user=candidate)
        return attrs

    def account_data(self):
        """Return account fields without the token or confirmation value."""

        return {
            key: self.validated_data[key]
            for key in ("username", "first_name", "last_name", "password")
        }
