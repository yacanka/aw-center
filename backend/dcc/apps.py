from django.apps import AppConfig


class DccConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dcc'

    def ready(self):
        """Register durable-job lifecycle projections."""

        from . import signals  # noqa: F401
