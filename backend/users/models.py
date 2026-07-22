from django.contrib.auth.models import Group, User
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.db.models.functions import Lower
from django.dispatch import receiver

class UserPreferences(models.Model):
    """User preferences model - extends default User via OneToOneField"""

    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System Default'),
    ]

    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('tr', 'Turkish'),
    ]

    TIMEZONE_CHOICES = [
        ('UTC', 'UTC'),
        ('America/New_York', 'Eastern Time'),
        ('America/Los_Angeles', 'Pacific Time'),
        ('Europe/London', 'London'),
        ('Europe/Paris', 'Paris'),
        ('Asia/Tokyo', 'Tokyo'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='preferences',
        primary_key=True
    )

    theme = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default='system'
    )

    has_particles = models.BooleanField(
        default=False,
        help_text='Show particles in the background'
    )

    language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default='en'
    )
    timezone = models.CharField(
        max_length=50,
        choices=TIMEZONE_CHOICES,
        default='UTC'
    )

    # Notification settings
    email_notifications = models.BooleanField(
        default=True,
        help_text='Receive email notifications'
    )
    push_notifications = models.BooleanField(
        default=True,
        help_text='Receive push notifications'
    )
    sms_notifications = models.BooleanField(
        default=False,
        help_text='Receive SMS notifications'
    )
    newsletter_subscribed = models.BooleanField(
        default=False,
        help_text='Subscribe to newsletter'
    )

    # Privacy settings
    profile_visible = models.BooleanField(
        default=True,
        help_text='Make profile visible to others'
    )
    show_online_status = models.BooleanField(
        default=True,
        help_text='Show online status to others'
    )
    show_activity = models.BooleanField(
        default=True,
        help_text='Show activity history to others'
    )

    # Display settings
    items_per_page = models.PositiveIntegerField(
        default=25,
        help_text='Number of items per page'
    )
    compact_view = models.BooleanField(
        default=False,
        help_text='Use compact view mode'
    )

    extra_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional custom settings'
    )

    jira_list = models.JSONField(
        default=list,
        blank=True,
        help_text='JIRA subtask list'
    )
    document_analysis_checks = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User Preference'
        verbose_name_plural = 'User Preferences'
        db_table = 'user_preferences'
        ordering = ['user__username', 'user_id']

    def __str__(self):
        return f"{self.user.username}'s Preferences"

    def get_extra_setting(self, key, default=None):
        return self.extra_settings.get(key, default)

    def set_extra_setting(self, key, value):
        self.extra_settings[key] = value
        self.save(update_fields=['extra_settings', 'updated_at'])

    def reset_to_defaults(self):
        self.theme = 'system'
        self.language = 'en'
        self.timezone = 'UTC'
        self.email_notifications = True
        self.push_notifications = True
        self.sms_notifications = False
        self.newsletter_subscribed = False
        self.profile_visible = True
        self.show_online_status = True
        self.show_activity = True
        self.items_per_page = 25
        self.compact_view = False
        self.extra_settings = {}
        self.jira_list = []
        self.document_analysis_checks = []
        self.save()


# Signal for NEW users only
@receiver(post_save, sender=User)
def create_user_preferences(sender, instance, created, **kwargs):
    if created:
        UserPreferences.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_preferences(sender, instance, **kwargs):
    # Save UserPreferences when User is saved
    if hasattr(instance, 'preferences'):
        instance.preferences.save()

def get_user_preferences(user):
    preferences, created = UserPreferences.objects.get_or_create(user=user)
    return preferences


# Monkey-patch User model for convenience (optional)
User.add_to_class('get_preferences', lambda self: get_user_preferences(self))


class UserInvitation(models.Model):
    """Represent one email-bound, single-use account invitation."""

    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    email = models.EmailField()
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="created_user_invitations"
    )
    groups = models.ManyToManyField(Group, blank=True, related_name="user_invitations")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="accepted_invitation"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["expires_at", "used_at"])]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=Q(used_at__isnull=True, revoked_at__isnull=True),
                name="users_one_open_invitation_per_email",
            )
        ]
