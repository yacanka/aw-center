import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DDF',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('project', models.CharField(max_length=255)),
                ('doc_name', models.CharField(max_length=255)),
                ('doc_no', models.CharField(max_length=255)),
                ('doc_issue', models.CharField(max_length=255)),
                ('date', models.CharField(max_length=255)),
                ('commentor', models.CharField(max_length=255)),
                ('comments', models.JSONField(default=list)),
                ('comment_types', models.JSONField(default=list)),
                ('path', models.CharField(blank=True, max_length=512, null=True)),
                ('created_time', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ddf', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_time', 'doc_no', 'id'],
            },
        ),
    ]
