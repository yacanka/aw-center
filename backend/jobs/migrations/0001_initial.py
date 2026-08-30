import django.db.models.deletion
import jobs.models
import jobs.storage
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(max_length=64)),
                ('title', models.CharField(max_length=160)),
                ('status', models.CharField(choices=[('awaiting_confirmation', 'Awaiting confirmation'), ('queued', 'Queued'), ('running', 'Running'), ('cancel_requested', 'Cancel requested'), ('cancelled', 'Cancelled'), ('succeeded', 'Succeeded'), ('failed', 'Failed'), ('reconciliation_required', 'Reconciliation required')], default='queued', max_length=24)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('message', models.CharField(blank=True, max_length=500)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('input_file', models.FileField(max_length=500, storage=jobs.storage.PrivateJobStorage(), upload_to=jobs.models.job_input_path)),
                ('input_name', models.CharField(max_length=180)),
                ('input_sha256', models.CharField(max_length=64)),
                ('output_file', models.FileField(blank=True, max_length=500, storage=jobs.storage.PrivateJobStorage(), upload_to=jobs.models.job_output_path)),
                ('output_name', models.CharField(blank=True, max_length=180)),
                ('output_sha256', models.CharField(blank=True, max_length=64)),
                ('result_summary', models.JSONField(blank=True, default=dict)),
                ('error_code', models.CharField(blank=True, max_length=64)),
                ('retryable', models.BooleanField(default=True)),
                ('reconcile_on_lease_loss', models.BooleanField(default=False)),
                ('idempotency_key', models.CharField(blank=True, max_length=128)),
                ('attempt', models.PositiveSmallIntegerField(default=1)),
                ('max_attempts', models.PositiveSmallIntegerField(default=3)),
                ('workflow_step', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('request_id', models.CharField(blank=True, max_length=64)),
                ('worker_id', models.CharField(blank=True, max_length=128)),
                ('execution_token', models.UUIDField(blank=True, editable=False, null=True)),
                ('lease_expires_at', models.DateTimeField(blank=True, null=True)),
                ('confirmation_expires_at', models.DateTimeField(blank=True, null=True)),
                ('cancel_requested_at', models.DateTimeField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='jobs', to=settings.AUTH_USER_MODEL)),
                ('retry_of', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='retry_attempts', to='jobs.job')),
                ('source_job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='handoff_jobs', to='jobs.job')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='JobEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('awaiting_confirmation', 'Awaiting confirmation'), ('queued', 'Queued'), ('running', 'Running'), ('cancel_requested', 'Cancel requested'), ('cancelled', 'Cancelled'), ('succeeded', 'Succeeded'), ('failed', 'Failed'), ('reconciliation_required', 'Reconciliation required')], max_length=24)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('message', models.CharField(blank=True, max_length=500)),
                ('code', models.CharField(blank=True, max_length=64)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='jobs.job')),
            ],
            options={
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='WorkerHeartbeat',
            fields=[
                ('worker_id', models.CharField(max_length=128, primary_key=True, serialize=False)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('heartbeat_at', models.DateTimeField(auto_now=True)),
                ('current_job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='jobs.job')),
            ],
            options={
                'ordering': ['-heartbeat_at'],
            },
        ),
        migrations.CreateModel(
            name='WorkflowRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('recipe', models.CharField(max_length=64)),
                ('title', models.CharField(max_length=160)),
                ('definition', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('cancel_requested', 'Cancel requested'), ('cancelled', 'Cancelled'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], default='queued', max_length=24)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('input_name', models.CharField(max_length=180)),
                ('input_sha256', models.CharField(max_length=64)),
                ('current_step', models.PositiveSmallIntegerField(default=1)),
                ('total_steps', models.PositiveSmallIntegerField()),
                ('message', models.CharField(blank=True, max_length=500)),
                ('error_code', models.CharField(blank=True, max_length=64)),
                ('idempotency_key', models.CharField(blank=True, max_length=128)),
                ('request_id', models.CharField(blank=True, max_length=64)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='workflow_runs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='job',
            name='workflow_run',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs', to='jobs.workflowrun'),
        ),
        migrations.CreateModel(
            name='WorkflowRunEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('cancel_requested', 'Cancel requested'), ('cancelled', 'Cancelled'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], max_length=24)),
                ('step', models.PositiveSmallIntegerField(default=1)),
                ('message', models.CharField(max_length=500)),
                ('code', models.CharField(blank=True, max_length=64)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('workflow', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='jobs.workflowrun')),
            ],
            options={
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='workflowrun',
            index=models.Index(fields=['owner', 'updated_at'], name='jobs_workfl_owner_i_eb6320_idx'),
        ),
        migrations.AddConstraint(
            model_name='workflowrun',
            constraint=models.UniqueConstraint(condition=models.Q(('idempotency_key', ''), _negated=True), fields=('owner', 'recipe', 'idempotency_key'), name='jobs_unique_owner_recipe_idempotency'),
        ),
        migrations.AddIndex(
            model_name='job',
            index=models.Index(fields=['status', 'created_at'], name='jobs_job_status_277b31_idx'),
        ),
        migrations.AddIndex(
            model_name='job',
            index=models.Index(fields=['owner', 'updated_at'], name='jobs_job_owner_i_5d0392_idx'),
        ),
        migrations.AddConstraint(
            model_name='job',
            constraint=models.UniqueConstraint(condition=models.Q(('idempotency_key', ''), _negated=True), fields=('owner', 'kind', 'idempotency_key'), name='jobs_unique_owner_kind_idempotency'),
        ),
        migrations.AddConstraint(
            model_name='job',
            constraint=models.UniqueConstraint(condition=models.Q(('retry_of__isnull', False)), fields=('retry_of',), name='jobs_unique_direct_retry'),
        ),
    ]
