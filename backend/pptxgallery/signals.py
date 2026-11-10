"""Presentation lifecycle hooks that keep private storage and projections aligned."""

from django.db import transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from jobs.models import Job, JobStatus
from jobs.storage import private_job_storage

from .models import Presentation, Slide


@receiver(pre_delete, sender=Job)
def retain_terminal_conversion_status(sender, instance, **_kwargs):
    """Preserve gallery status when retained Job audit rows expire."""

    status_value = "ready" if instance.status == JobStatus.SUCCEEDED else "failed"
    Presentation.objects.filter(conversion_job=instance).update(status=status_value)


@receiver(post_delete, sender=Presentation)
def delete_presentation_source(sender, instance, **_kwargs):
    """Delete a private source only after its database deletion commits."""

    _delete_on_commit(instance.file.name)


@receiver(post_delete, sender=Slide)
def delete_slide_files(sender, instance, **_kwargs):
    """Delete private slide images only after their database deletion commits."""

    _delete_on_commit(instance.image.name, instance.thumb.name)


def _delete_on_commit(*names):
    safe_names = tuple(name for name in names if name)
    transaction.on_commit(lambda: _delete_all(safe_names))


def _delete_all(names):
    for name in names:
        private_job_storage.delete(name)
