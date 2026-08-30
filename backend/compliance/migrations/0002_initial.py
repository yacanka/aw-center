import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('compliance', '0001_initial'),
        ('orgs', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='documentpurgeaudit',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='compliance_document_purge_audits', to='orgs.project'),
        ),
        migrations.AddField(
            model_name='compliancedocument',
            name='panel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='compliance_documents', to='orgs.panel'),
        ),
        migrations.AddField(
            model_name='compliancedocument',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compliance_documents', to='orgs.project'),
        ),
        migrations.AddField(
            model_name='coverpage',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cover_pages', to='orgs.project'),
        ),
        migrations.AddField(
            model_name='compliancedocument',
            name='cover_page',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='compliance_documents', to='compliance.coverpage'),
        ),
        migrations.AddField(
            model_name='historicalcompliancedocument',
            name='archived_by',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='historicalcompliancedocument',
            name='cover_page',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='compliance.coverpage'),
        ),
        migrations.AddField(
            model_name='historicalcompliancedocument',
            name='history_user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='historicalcompliancedocument',
            name='owner',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='historicalcompliancedocument',
            name='owner_group',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='auth.group'),
        ),
        migrations.AddField(
            model_name='historicalcompliancedocument',
            name='panel',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='orgs.panel'),
        ),
        migrations.AddField(
            model_name='historicalcompliancedocument',
            name='project',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='orgs.project'),
        ),
        migrations.AddField(
            model_name='historicalcoverpage',
            name='history_user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='historicalcoverpage',
            name='project',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='orgs.project'),
        ),
        migrations.AddField(
            model_name='importaudit',
            name='imported_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compliance_import_audits', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='importaudit',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compliance_import_audits', to='orgs.project'),
        ),
        migrations.AddField(
            model_name='notificationpolicy',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compliance_notification_policies', to='orgs.project'),
        ),
        migrations.AddField(
            model_name='notificationpolicy',
            name='updated_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compliance_notification_policy_revisions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='reviewtask',
            name='assignee',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compliance_review_tasks', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='reviewtask',
            name='decided_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='decided_compliance_reviews', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='reviewtask',
            name='document',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_tasks', to='compliance.compliancedocument'),
        ),
        migrations.AddField(
            model_name='reviewtask',
            name='requested_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requested_compliance_reviews', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='trackingprofile',
            name='document',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='tracking_profile', to='compliance.compliancedocument'),
        ),
        migrations.AddField(
            model_name='trackingprofile',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_compliance_tracking_profiles', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='trackingprofile',
            name='responsible_people',
            field=models.ManyToManyField(blank=True, related_name='compliance_tracking_profiles', to='orgs.person'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='profile',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_logs', to='compliance.trackingprofile'),
        ),
        migrations.AddField(
            model_name='workflowevent',
            name='actor',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='workflowevent',
            name='document',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='workflow_events', to='compliance.compliancedocument'),
        ),
        migrations.AddConstraint(
            model_name='coverpage',
            constraint=models.UniqueConstraint(fields=('project', 'number'), name='compliance_unique_project_cover_page'),
        ),
        migrations.AddIndex(
            model_name='compliancedocument',
            index=models.Index(fields=['project', 'is_archived', 'status'], name='compliance__project_c641f8_idx'),
        ),
        migrations.AddIndex(
            model_name='compliancedocument',
            index=models.Index(fields=['project', 'next_action_due_date'], name='compliance__project_335f70_idx'),
        ),
        migrations.AddConstraint(
            model_name='compliancedocument',
            constraint=models.UniqueConstraint(fields=('project', 'cover_page', 'name'), name='compliance_unique_cover_page_document_name'),
        ),
        migrations.AddConstraint(
            model_name='compliancedocument',
            constraint=models.UniqueConstraint(condition=models.Q(('tech_doc_no__isnull', False), models.Q(('tech_doc_no', ''), _negated=True)), fields=('project', 'cover_page', 'tech_doc_no'), name='compliance_unique_cover_page_tech_doc'),
        ),
        migrations.AddIndex(
            model_name='documentpurgeaudit',
            index=models.Index(fields=['project', 'purged_at'], name='compliance__project_234de6_idx'),
        ),
        migrations.AddIndex(
            model_name='importaudit',
            index=models.Index(fields=['project', 'started_at'], name='compliance__project_af2910_idx'),
        ),
        migrations.AddConstraint(
            model_name='notificationpolicy',
            constraint=models.UniqueConstraint(fields=('project', 'version'), name='compliance_unique_project_policy_version'),
        ),
        migrations.AddConstraint(
            model_name='notificationpolicy',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('project',), name='compliance_unique_active_project_policy'),
        ),
        migrations.AddIndex(
            model_name='reviewtask',
            index=models.Index(fields=['document', 'status'], name='compliance__documen_346178_idx'),
        ),
        migrations.AddIndex(
            model_name='reviewtask',
            index=models.Index(fields=['assignee', 'status', 'due_date'], name='compliance__assigne_f038ac_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['status', 'next_attempt_at'], name='compliance__status_dd4919_idx'),
        ),
        migrations.AddIndex(
            model_name='workflowevent',
            index=models.Index(fields=['document', 'created_at'], name='compliance__documen_714a0d_idx'),
        ),
        migrations.AddConstraint(
            model_name='workflowevent',
            constraint=models.UniqueConstraint(fields=('document', 'sequence'), name='compliance_unique_document_workflow_sequence'),
        ),
    ]
