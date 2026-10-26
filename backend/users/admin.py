from django import forms
from django.contrib import admin, messages
from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, AdminUserCreationForm, AuthenticationForm, UserChangeForm
from django.core.validators import MaxLengthValidator
from django.db import IntegrityError
from django.http import HttpResponseRedirect

from .models import PasswordResetDelivery, UserInvitation, UserPreferences
from .email_policy import EMAIL_UNAVAILABLE, is_email_identity_conflict, validate_email_identity
from .password_policy import MAX_PASSWORD_LENGTH
from .username_policy import validate_username_format


class BoundedPasswordFormMixin:
    """Keep Django's password widgets/help text and apply the browser limit."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("password", "password1", "password2"):
            if name in self.fields:
                field = self.fields[name]
                field.strip = False
                field.max_length = MAX_PASSWORD_LENGTH
                field.validators.append(MaxLengthValidator(MAX_PASSWORD_LENGTH))
                field.widget.attrs["maxlength"] = MAX_PASSWORD_LENGTH


class EmailIdentityFormMixin:
    def clean_email(self):
        return validate_email_identity(self.cleaned_data["email"], user=self.instance)


class ConstrainedUserCreationForm(EmailIdentityFormMixin, BoundedPasswordFormMixin, AdminUserCreationForm):
    def clean_username(self):
        username = super().clean_username()
        validate_username_format(username)
        return username


class ConstrainedAdminAuthenticationForm(BoundedPasswordFormMixin, AuthenticationForm):
    username = forms.CharField(max_length=6, validators=[validate_username_format])


class ConstrainedUserChangeForm(EmailIdentityFormMixin, UserChangeForm):
    def clean_username(self):
        username = self.cleaned_data["username"]
        validate_username_format(username)
        return username


class ConstrainedAdminPasswordChangeForm(BoundedPasswordFormMixin, AdminPasswordChangeForm):
    pass


class SuperuserAuthWriteAdminMixin:
    """Django auth model permissions also power the deliberately limited API."""

    @staticmethod
    def _can_manage_auth(request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return self._can_manage_auth(request)

    def has_change_permission(self, request, obj=None):
        return self._can_manage_auth(request)

    def has_delete_permission(self, request, obj=None):
        return self._can_manage_auth(request)


class UserPreferencesInline(admin.StackedInline):
    model = UserPreferences
    can_delete = False
    verbose_name = 'Preferences'
    verbose_name_plural = 'Preferences'
    readonly_fields = ('extra_settings', 'version')

    fieldsets = (
        ('Appearance', {
            'fields': ('theme', 'language', 'timezone'),
            'classes': ('wide',)
        }),
        ('Notifications', {
            'fields': (
                'email_notifications',
                'push_notifications',
                'sms_notifications',
                'newsletter_subscribed'
            ),
        }),
        ('Privacy', {
            'fields': (
                'profile_visible',
                'show_online_status',
                'show_activity'
            ),
        }),
        ('Display', {
            'fields': ('items_per_page', 'compact_view'),
        }),
        ('Advanced', {
            'fields': ('extra_settings',),
            'classes': ('collapse',),
        }),
    )


class CustomUserAdmin(SuperuserAuthWriteAdminMixin, UserAdmin):
    add_form = ConstrainedUserCreationForm
    form = ConstrainedUserChangeForm
    change_password_form = ConstrainedAdminPasswordChangeForm
    inlines = (UserPreferencesInline,)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except IntegrityError as error:
            if not is_email_identity_conflict(error):
                raise
            # UserAdmin has rolled back its complete form/inline transaction.
            self.message_user(request, EMAIL_UNAVAILABLE, level=messages.ERROR)
            return HttpResponseRedirect(request.path)

    def save_formset(self, request, form, formset, change):
        if formset.model is not UserPreferences:
            return super().save_formset(request, form, formset, change)
        from .preference_service import update_user_preferences
        # Initialize Django's change-message bookkeeping without bypassing the
        # preference service's versioned writes.
        formset.save(commit=False)
        for inline_form in formset.forms:
            if inline_form.has_changed():
                values = {name: inline_form.cleaned_data[name] for name in inline_form.changed_data
                          if name not in {'user', 'extra_settings', 'version', 'DELETE', 'id'}}
                update_user_preferences(form.instance, values)
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'get_theme',
        'get_language'
    )
    list_filter = UserAdmin.list_filter + ('preferences__theme', 'preferences__language')

    def get_theme(self, obj):
        if hasattr(obj, 'preferences'):
            return obj.preferences.get_theme_display()
        return '-'
    get_theme.short_description = 'Theme'
    get_theme.admin_order_field = 'preferences__theme'

    def get_language(self, obj):
        if hasattr(obj, 'preferences'):
            return obj.preferences.get_language_display()
        return '-'
    get_language.short_description = 'Language'
    get_language.admin_order_field = 'preferences__language'


# Unregister default User admin and register custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.unregister(Group)


@admin.register(Group)
class CustomGroupAdmin(SuperuserAuthWriteAdminMixin, GroupAdmin):
    pass


admin.site.login_form = ConstrainedAdminAuthenticationForm


# Standalone UserPreferences admin (optional)
@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'theme', 'language', 'email_notifications', 'updated_at')
    list_filter = ('theme', 'language', 'email_notifications')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'created_at', 'updated_at', 'extra_settings', 'version')

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        from .preference_service import update_user_preferences
        update_user_preferences(obj.user, {name: getattr(obj, name) for name in form.changed_data})


@admin.register(UserInvitation)
class UserInvitationAdmin(admin.ModelAdmin):
    """Expose invitation audit state without any recoverable raw token."""

    list_display = ('email', 'created_by', 'created_at', 'expires_at', 'used_at', 'revoked_at')
    search_fields = ('email', 'created_by__username', 'used_by__username')
    readonly_fields = (
        'token_digest', 'email', 'created_by', 'groups', 'created_at',
        'expires_at', 'used_at', 'used_by', 'revoked_at',
    )

    def has_add_permission(self, request):
        """Require secure application services for invitation creation."""

        return False


@admin.register(PasswordResetDelivery)
class PasswordResetDeliveryAdmin(admin.ModelAdmin):
    """Read-only delivery audit; no password-reset token is persisted."""

    list_display = (
        "id",
        "user",
        "status",
        "attempt_count",
        "requested_at",
        "sent_at",
        "error_code",
    )
    list_filter = ("status", "error_code")
    search_fields = ("user__username", "user__email")
    readonly_fields = (
        "id",
        "user",
        "state_digest",
        "token_timestamp",
        "message_id",
        "status",
        "error_code",
        "attempt_count",
        "lease_token",
        "claimed_at",
        "claim_expires_at",
        "next_attempt_at",
        "requested_at",
        "sent_at",
        "cancelled_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
