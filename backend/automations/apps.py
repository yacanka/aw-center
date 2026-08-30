from django.apps import AppConfig


class AutomationsConfig(AppConfig):
    """Configure server-owned automation workflows."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "automations"

    def ready(self):
        """Register private source lifecycle cleanup."""

        from . import signals  # noqa: F401
