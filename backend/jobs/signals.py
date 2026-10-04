import logging
from functools import partial

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Job


logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Job)
def delete_job_artifacts(sender, instance, using, **kwargs):
    """Delete captured private artifacts only after the database deletion commits."""

    artifacts = tuple(
        (field.storage, field.name)
        for field in (instance.input_file, instance.output_file)
        if field and field.name
    )
    transaction.on_commit(
        partial(_delete_artifacts, artifacts, str(instance.pk)), using=using
    )


def _delete_artifacts(artifacts, job_id):
    for storage, name in artifacts:
        try:
            storage.delete(name)
        except OSError as error:
            # The database is already committed. Retention retries orphan files;
            # one locked file must not prevent deletion of the other artifact.
            logger.warning(
                "Job artifact cleanup deferred to retention.",
                extra={"job_id": job_id, "error_type": type(error).__name__},
            )
