from django.apps import AppConfig


class LegacyDccMigrationsConfig(AppConfig):
    name = "integrations.jira.legacy_dcc"
    label = "dcc"
    default_auto_field = "django.db.models.BigAutoField"
