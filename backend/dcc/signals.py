"""Project durable publication-job terminals onto their DCC draft."""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="jobs.Job")
def project_dcc_publication_job_state(sender, instance, **kwargs):
    """Keep the review aggregate aligned with its authoritative durable job."""

    from .issue_draft_publication_state import project_publication_job_terminal

    project_publication_job_terminal(instance)
