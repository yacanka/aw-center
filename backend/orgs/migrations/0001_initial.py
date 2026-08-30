import django.core.validators
import django.db.models.deletion
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
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('person_id', models.CharField(db_index=True, max_length=32, unique=True)),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('email', models.EmailField(db_index=True, max_length=254)),
            ],
            options={
                'ordering': ['name', 'person_id'],
                'permissions': [('manage_people_directory', 'Can manage the global people directory')],
            },
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('slug', models.SlugField(unique=True)),
                ('enabled', models.BooleanField(db_index=True, default=True)),
            ],
            options={
                'ordering': ['name', 'id'],
                'permissions': [('manage_project_roles', 'Can manage project role assignments')],
            },
        ),
        migrations.CreateModel(
            name='Panel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('discipline', models.CharField(blank=True, max_length=255)),
                ('ata', models.CharField(max_length=5, validators=[django.core.validators.RegexValidator('^[0-9]{2}-[0-9]{2}$', message='ATA chapter must consist of four digits (XX-XX).')])),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='panels', to='orgs.project')),
            ],
            options={
                'ordering': ['project__name', 'ata', 'name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ProjectRoleAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('domain', models.CharField(choices=[('compliance', 'Compliance documents'), ('organization', 'Organization'), ('dcc', 'DCC')], max_length=16)),
                ('role', models.CharField(choices=[('viewer', 'Viewer'), ('editor', 'Editor'), ('manager', 'Manager'), ('operator', 'Operator'), ('publisher', 'Publisher')], max_length=16)),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='project_role_assignments', to='auth.group')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='role_assignments', to='orgs.project')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='project_role_assignments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['project__name', 'domain', 'role', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ResponsibleAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('responsibility_role', models.CharField(choices=[('AS', 'AS'), ('CVE', 'CVE'), ('PSK', 'PSK'), ('IPT', 'IPT'), ('SSB', 'SSB'), ('Air Force', 'Air Force'), ('PCE', 'PCE')], max_length=32)),
                ('panel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='responsible_assignments', to='orgs.panel')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='responsible_assignments', to='orgs.person')),
            ],
            options={
                'ordering': ['panel__project__name', 'panel__ata', 'person__name', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='panel',
            constraint=models.UniqueConstraint(fields=('project', 'ata'), name='orgs_unique_project_panel_ata'),
        ),
        migrations.AddConstraint(
            model_name='projectroleassignment',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('group__isnull', True), ('user__isnull', False)), models.Q(('group__isnull', False), ('user__isnull', True)), _connector='OR'), name='orgs_project_role_exactly_one_subject'),
        ),
        migrations.AddConstraint(
            model_name='projectroleassignment',
            constraint=models.UniqueConstraint(condition=models.Q(('user__isnull', False)), fields=('project', 'domain', 'user'), name='orgs_unique_project_domain_user_role'),
        ),
        migrations.AddConstraint(
            model_name='projectroleassignment',
            constraint=models.UniqueConstraint(condition=models.Q(('group__isnull', False)), fields=('project', 'domain', 'group'), name='orgs_unique_project_domain_group_role'),
        ),
        migrations.AddConstraint(
            model_name='responsibleassignment',
            constraint=models.UniqueConstraint(fields=('panel', 'person', 'responsibility_role'), name='orgs_unique_panel_person_responsibility'),
        ),
    ]
