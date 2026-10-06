"""ECR domain events and private artifact lifecycle handlers."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import Signal, receiver

from .models import EcrWorkflow


# Sent synchronously inside publication completion so receiver failures roll back
# the workflow and its dependent writes together. Payload: owner, issue, title, projects.
ecr_publication_completed = Signal()


@receiver(post_delete, sender=EcrWorkflow)
def delete_ecr_source(sender, instance, **kwargs):
    """Remove the private PDF after an explicitly deleted workflow."""

    source = instance.source_pdf
    if source and source.name:
        source.storage.delete(source.name)


@receiver(post_save, sender="jobs.Job")
def project_ecr_job_state(sender, instance, **kwargs):
    """Project terminal job state without making browser GET endpoints write."""

    from .ecr_services import project_ecr_job_terminal

    project_ecr_job_terminal(instance)
