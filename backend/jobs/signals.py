from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Job


@receiver(post_delete, sender=Job)
def delete_job_artifacts(sender, instance, **kwargs):
    """Delete private input and output artifacts when their job is removed."""

    for field in (instance.input_file, instance.output_file):
        if field and field.name:
            field.storage.delete(field.name)
