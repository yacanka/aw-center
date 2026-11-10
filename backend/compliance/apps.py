from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "compliance"
    verbose_name = "Compliance Documents"

    def ready(self):
        from django.db.models.signals import post_save
        from orgs.models import Project
        from .signals import create_default_status
        post_save.connect(create_default_status, sender=Project, dispatch_uid="compliance.default_status")
