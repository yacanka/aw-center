import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ReleaseNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.CharField(max_length=32, unique=True)),
                ('title', models.CharField(max_length=200)),
                ('is_active', models.BooleanField(default=True)),
                ('published_at', models.DateTimeField(auto_now_add=True)),
                ('requires_ack', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ['-published_at'],
            },
        ),
        migrations.CreateModel(
            name='ReleaseNoteItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_type', models.CharField(choices=[('feature', 'Feature'), ('fix', 'Fix'), ('breaking', 'Breaking'), ('info', 'Info'), ('security', 'Security')], max_length=16)),
                ('heading', models.CharField(blank=True, default='', max_length=200)),
                ('body_md', models.TextField()),
                ('order', models.PositiveIntegerField(default=0)),
                ('release_note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='releases.releasenote')),
            ],
            options={
                'ordering': ['order', 'id'],
                'indexes': [models.Index(fields=['release_note', 'item_type'], name='releases_re_release_4f2a77_idx')],
            },
        ),
        migrations.CreateModel(
            name='ReleaseNoteSeen',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seen_at', models.DateTimeField(auto_now_add=True)),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('release_note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seen_by', to='releases.releasenote')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='release_notes_seen', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-seen_at', 'user_id', 'release_note_id'],
                'indexes': [models.Index(fields=['user', 'release_note'], name='releases_re_user_id_0f7d87_idx'), models.Index(fields=['user', 'seen_at'], name='releases_re_user_id_4c4eba_idx')],
                'unique_together': {('user', 'release_note')},
            },
        ),
    ]
