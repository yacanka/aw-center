from django.apps import apps
from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.urls import path, reverse


PROJECT_ADMIN_APP_LABELS = frozenset(
    {
        'aesa',
        'blok30',
        'blok4050',
        'gokbey',
        'havasoj',
        'hys',
        'ozgur',
        'piku',
    }
)
PROJECTS_ADMIN_APP_LABEL = 'projects'
PROJECTS_ADMIN_APP_NAME = 'Projects'


class AwCenterAdminSite(AdminSite):
    """Admin site that groups project-specific apps under one section."""

    def get_urls(self):
        """Add a synthetic Projects app index URL to Django admin."""
        custom_urls = [
            path(
                f'{PROJECTS_ADMIN_APP_LABEL}/',
                self.admin_view(self.app_index),
                {'app_label': PROJECTS_ADMIN_APP_LABEL},
                name='projects_app_list',
            )
        ]
        return custom_urls + super().get_urls()

    def get_app_list(self, request, app_label=None):
        """Return Django admin apps with project apps merged into Projects."""
        source_app_label = None if app_label == PROJECTS_ADMIN_APP_LABEL else app_label
        app_list = super().get_app_list(request, source_app_label)
        if app_label and app_label != PROJECTS_ADMIN_APP_LABEL:
            return app_list
        grouped_app_list = self._group_project_apps(request, app_list)
        if app_label == PROJECTS_ADMIN_APP_LABEL:
            return [app for app in grouped_app_list if app['app_label'] == PROJECTS_ADMIN_APP_LABEL]
        return grouped_app_list

    def _group_project_apps(self, request, app_list):
        grouped_app = self._build_projects_app(request, app_list)
        filtered_app_list = [
            app for app in app_list if app['app_label'] not in PROJECT_ADMIN_APP_LABELS
        ]
        if grouped_app['models']:
            filtered_app_list.append(grouped_app)
        return sorted(filtered_app_list, key=lambda app: app['name'].lower())

    def _build_projects_app(self, request, app_list):
        models = []
        for app in app_list:
            if app['app_label'] in PROJECT_ADMIN_APP_LABELS:
                models.extend(self._get_project_models(app))
        return {
            'name': PROJECTS_ADMIN_APP_NAME,
            'app_label': PROJECTS_ADMIN_APP_LABEL,
            'app_url': self._get_projects_app_url(request),
            'has_module_perms': bool(models),
            'models': sorted(models, key=lambda model: model['name'].lower()),
        }

    def _get_project_models(self, app):
        project_name = apps.get_app_config(app['app_label']).verbose_name
        project_models = []
        for model in app['models']:
            project_model = model.copy()
            project_model['name'] = f"{project_name} {model['name']}"
            project_models.append(project_model)
        return project_models

    def _get_projects_app_url(self, request):
        return reverse('admin:projects_app_list', current_app=self.name)


class AwCenterAdminConfig(AdminConfig):
    """Use the AW Center admin site configuration."""

    default_site = 'awcenter.admin.AwCenterAdminSite'
