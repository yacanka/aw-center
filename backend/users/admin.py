from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

from .models import UserInvitation, UserPreferences

class UserPreferencesInline(admin.StackedInline):
    model = UserPreferences
    can_delete = False
    verbose_name = 'Preferences'
    verbose_name_plural = 'Preferences'

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


class CustomUserAdmin(UserAdmin):
    inlines = (UserPreferencesInline,)
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


# Standalone UserPreferences admin (optional)
@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'theme', 'language', 'email_notifications', 'updated_at')
    list_filter = ('theme', 'language', 'email_notifications')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


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
