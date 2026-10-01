"""Initialize the default vocabulary for newly created projects."""


def create_default_status(sender, instance, created, raw=False, using="default", **kwargs):
    if created and not raw:
        from .models import DocumentStatus
        DocumentStatus.objects.using(using).get_or_create(
            project_id=instance.pk, value="unknown", defaults={"label": "Unknown"},
        )
