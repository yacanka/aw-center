from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
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
    
    # Additional settings
    extra_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional custom settings'
    )
    
    jira_list = models.JSONField(
        default=dict,
        blank=True,
        help_text='JIRA subtask list'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User Preference'
        verbose_name_plural = 'User Preferences'
        db_table = 'user_preferences'
    
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