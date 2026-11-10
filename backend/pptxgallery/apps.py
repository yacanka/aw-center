from django.apps import AppConfig


class PptxgalleryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pptxgallery"

    def ready(self):
        """Register private-file and retained-status lifecycle handlers."""

        from . import signals  # noqa: F401
