import django.db.models.deletion
import django.db.models.functions.text
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserPreferences',
            fields=[
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='preferences', serialize=False, to=settings.AUTH_USER_MODEL)),
                ('theme', models.CharField(choices=[('light', 'Light'), ('dark', 'Dark'), ('system', 'System Default')], default='system', max_length=10)),
                ('has_particles', models.BooleanField(default=False, help_text='Show particles in the background')),
                ('language', models.CharField(choices=[('en', 'English'), ('tr', 'Turkish')], default='en', max_length=5)),
                ('timezone', models.CharField(choices=[('UTC', 'UTC'), ('America/New_York', 'Eastern Time'), ('America/Los_Angeles', 'Pacific Time'), ('Europe/London', 'London'), ('Europe/Paris', 'Paris'), ('Asia/Tokyo', 'Tokyo')], default='UTC', max_length=50)),
                ('email_notifications', models.BooleanField(default=True, help_text='Receive email notifications')),
                ('push_notifications', models.BooleanField(default=True, help_text='Receive push notifications')),
                ('sms_notifications', models.BooleanField(default=False, help_text='Receive SMS notifications')),
                ('newsletter_subscribed', models.BooleanField(default=False, help_text='Subscribe to newsletter')),
                ('profile_visible', models.BooleanField(default=True, help_text='Make profile visible to others')),
                ('show_online_status', models.BooleanField(default=True, help_text='Show online status to others')),
                ('show_activity', models.BooleanField(default=True, help_text='Show activity history to others')),
                ('items_per_page', models.PositiveIntegerField(default=25, help_text='Number of items per page')),
                ('compact_view', models.BooleanField(default=False, help_text='Use compact view mode')),
                ('extra_settings', models.JSONField(blank=True, default=dict, help_text='Additional custom settings')),
                ('jira_list', models.JSONField(blank=True, default=list, help_text='JIRA subtask list')),
                ('document_analysis_checks', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'User Preference',
                'verbose_name_plural': 'User Preferences',
                'db_table': 'user_preferences',
                'ordering': ['user__username', 'user_id'],
            },
        ),
        migrations.CreateModel(
            name='UserInvitation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_digest', models.CharField(editable=False, max_length=64, unique=True)),
                ('email', models.EmailField(max_length=254)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_user_invitations', to=settings.AUTH_USER_MODEL)),
                ('groups', models.ManyToManyField(blank=True, related_name='user_invitations', to='auth.group')),
                ('used_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='accepted_invitation', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['expires_at', 'used_at'], name='users_useri_expires_d265dc_idx')],
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('email'), condition=models.Q(('revoked_at__isnull', True), ('used_at__isnull', True)), name='users_one_open_invitation_per_email')],
            },
        ),
        migrations.CreateModel(
            name='PasswordResetDelivery',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('state_digest', models.CharField(editable=False, max_length=64)),
                ('token_timestamp', models.PositiveBigIntegerField(editable=False)),
                ('message_id', models.CharField(editable=False, max_length=255, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('claimed', 'Claimed'), ('sent', 'Sent'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=16)),
                ('error_code', models.CharField(blank=True, max_length=64)),
                ('attempt_count', models.PositiveSmallIntegerField(default=0)),
                ('lease_token', models.UUIDField(blank=True, editable=False, null=True)),
                ('claimed_at', models.DateTimeField(blank=True, null=True)),
                ('claim_expires_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('next_attempt_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('requested_at', models.DateTimeField()),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='password_reset_deliveries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['requested_at', 'id'],
                'indexes': [models.Index(fields=['status', 'next_attempt_at'], name='users_passw_status_898c9c_idx')],
            },
        ),
    ]
