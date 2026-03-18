from rest_framework.serializers import Serializer, ModelSerializer, CharField, SerializerMethodField
from django.contrib.auth.models import User, Permission, ContentType
from django.core.exceptions import ValidationError

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import serializers

from .models import UserPreferences
from dcc.service.MailSender import *

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
            'theme',
            'has_particles',
            'language',
            'timezone',
            'email_notifications',
            'push_notifications',
            'sms_notifications',
            'newsletter_subscribed',
            'profile_visible',
            'show_online_status',
            'show_activity',
            'items_per_page',
            'compact_view',
            'extra_settings',
            'updated_at',
            'jira_list'
        ]
        read_only_fields = ['updated_at']

class UserSerializer(ModelSerializer):
    password = CharField(write_only=True)
    permissions = PermissionSerializer(source="user_permissions", many=True, read_only=True)
    preferences = UserPreferencesSerializer(required=False)
    
    class Meta:
        model = User
        fields = ["id", "password", "username", "email", "first_name", "last_name", "groups", "permissions", "user_permissions", "last_login", "preferences"]
        
    def get_permissions(self, obj):
        return list(obj.get_all_permissions())

    def create(self, data):
        user = User.objects.create_user(
            username=data["username"],
            password=data["password"],
            email=data.get("email", ""),
            first_name= data.get("first_name", ""),
            last_name= data.get("last_name", "")
        )
        return user
    
    def update(self, instance, data):
        password = data.pop("password",  None)
        permissions = data.pop("user_permissions",  None)
        preferences_data = data.pop('preferences', None)
        
        instance = super().update(instance, data)

        if password:
            instance.set_password(password)
        if permissions is not None:
            instance.user_permissions.set(permissions)
            
        if preferences_data and hasattr(instance, 'preferences'):
            preferences = instance.preferences
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
            raise ValidationError("Current password is wrong.")
        
        if data["new_password"] != data["confirm_password"]:
            raise ValidationError("New passwords are not match.")
        
        return data


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self):
        request = self.context["request"]
        email = self.validated_data["email"]

        # Kullanıcı var/yok bilgisini sızdırmamak için her durumda 200 döneceğiz.
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = token_generator.make_token(user)

        # SPA URL’ini settings’ten al
        frontend_reset_url = getattr(settings, "FRONTEND_RESET_URL", None)
        # örn: https://app.domain.com/reset-password
        reset_link = f"{frontend_reset_url}?uid={uid}&token={token}"

        mail_placeholder = {
            "{{RESET_LINK}}": reset_link,
        }

        html_file_path = TEMPLATE_DIR / "mail_password_reset_request_template.html"
        mail_title = "Şifre sıfırlama"

        content = html_to_text(html_file_path)
        content = replace_all_keys(content, mail_placeholder)

        to_list = user.email
        cc_list = ""
        
        SendMail(mail_title, content, to_list, cc_list)


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
        except Exception:
            raise serializers.ValidationError({"detail": "Invalid link."})

        if not token_generator.check_token(user, token):
            raise serializers.ValidationError({"detail": "Token is invalid or has expired."})

        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return user

