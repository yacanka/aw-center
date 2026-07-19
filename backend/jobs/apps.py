from django.apps import AppConfig


class JobsConfig(AppConfig):
    """Configure durable background jobs."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "jobs"

    def ready(self):
        """Register artifact lifecycle cleanup signals."""

        from . import signals  # noqa: F401
