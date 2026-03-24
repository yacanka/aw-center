from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import ContentType, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework.serializers import CharField, ModelSerializer, Serializer

from dcc.service.MailSender import SendMail, html_to_text, replace_all_keys
from .models import UserPreferences

TEMPLATE_DIR = settings.CUSTOM_TEMPLATE_DIR
User = get_user_model()
token_generator = PasswordResetTokenGenerator()


class ContentTypeSerializer(ModelSerializer):
    class Meta:
        model = ContentType
        fields = ["app_label", "model"]


class PermissionSerializer(ModelSerializer):
    content_type = ContentTypeSerializer()

    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "content_type"]


class UserPreferencesSerializer(ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = [
            "theme",
            "has_particles",
            "language",
            "timezone",
            "email_notifications",
            "push_notifications",
            "sms_notifications",
            "newsletter_subscribed",
            "profile_visible",
            "show_online_status",
            "show_activity",
            "items_per_page",
            "compact_view",
            "extra_settings",
            "updated_at",
            "jira_list",
        ]
        read_only_fields = ["updated_at"]


class UserSerializer(ModelSerializer):
    password = CharField(write_only=True, required=False, allow_blank=False)
    permissions = PermissionSerializer(source="user_permissions", many=True, read_only=True)
    preferences = UserPreferencesSerializer(required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "password",
            "username",
            "email",
            "first_name",
            "last_name",
            "groups",
            "permissions",
            "user_permissions",
            "last_login",
            "is_superuser",
            "is_staff",
            "is_active",
            "date_joined",
            "preferences",
        ]
        read_only_fields = [
            "id",
            "last_login",
            "is_superuser",
            "is_staff",
            "is_active",
            "date_joined",
        ]
        extra_kwargs = {
            "groups": {"required": False},
            "user_permissions": {"required": False},
            "email": {"required": False},
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def _can_manage_auth_fields(self):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return request.user.has_perm("auth.change_user")

    def validate(self, attrs):
        restricted_fields = {"groups", "user_permissions"}
        if not self._can_manage_auth_fields() and restricted_fields.intersection(attrs.keys()):
            raise serializers.ValidationError(
                {"detail": "You are not allowed to modify groups or permissions."}
            )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        groups = validated_data.pop("groups", None)
        permissions = validated_data.pop("user_permissions", None)
        preferences_data = validated_data.pop("preferences", None)

        if not password:
            raise serializers.ValidationError({"password": "Password is required."})

        candidate_user = User(**validated_data)
        validate_password(password, user=candidate_user)

        user = User.objects.create_user(password=password, **validated_data)

        if self._can_manage_auth_fields():
            if groups is not None:
                user.groups.set(groups)
            if permissions is not None:
                user.user_permissions.set(permissions)

        if preferences_data:
            preferences, _ = UserPreferences.objects.get_or_create(user=user)
            for attr, value in preferences_data.items():
                setattr(preferences, attr, value)
            preferences.save()

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        groups = validated_data.pop("groups", None)
        permissions = validated_data.pop("user_permissions", None)
        preferences_data = validated_data.pop("preferences", None)

        instance = super().update(instance, validated_data)

        if password:
            validate_password(password, user=instance)
            instance.set_password(password)
            instance.save(update_fields=["password"])

        if self._can_manage_auth_fields():
            if groups is not None:
                instance.groups.set(groups)
            if permissions is not None:
                instance.user_permissions.set(permissions)

        if preferences_data:
            preferences, _ = UserPreferences.objects.get_or_create(user=instance)
            for attr, value in preferences_data.items():
                setattr(preferences, attr, value)
            preferences.save()

        return instance


class PasswordChangeSerializer(Serializer):
    current_password = CharField(write_only=True)
    new_password = CharField(write_only=True)
    confirm_password = CharField(write_only=True)

    def validate(self, data):
        user = self.context["request"].user
        if not user.check_password(data["current_password"]):
            raise serializers.ValidationError("Current password is wrong.")

        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError("New passwords do not match.")

        validate_password(data["new_password"], user=user)
        return data


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self):
        email = self.validated_data["email"]

        # Kullanıcı var/yok bilgisini sızdırmamak için her durumda 200 döneceğiz.
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = token_generator.make_token(user)
        reset_link = f"{settings.FRONTEND_RESET_URL}?uid={uid}&token={token}"

        mail_placeholder = {
            "{{RESET_LINK}}": reset_link,
        }

        html_file_path = TEMPLATE_DIR / "mail_password_reset_request_template.html"
        mail_title = "Şifre sıfırlama"

        content = html_to_text(html_file_path)
        content = replace_all_keys(content, mail_placeholder)

        SendMail(mail_title, content, user.email, "")


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)

    def validate(self, attrs):
        uid = attrs["uid"]
        token = attrs["token"]

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)
        except Exception as exc:
            raise serializers.ValidationError({"detail": "Invalid link."}) from exc

        if not token_generator.check_token(user, token):
            raise serializers.ValidationError({"detail": "Token is invalid or has expired."})

        validate_password(attrs["new_password"], user=user)
        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return user

