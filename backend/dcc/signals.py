"""Project publication lifecycle events onto DCC records and drafts."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from automations.signals import ecr_publication_completed


@receiver(post_save, sender="jobs.Job")
def project_dcc_publication_job_state(sender, instance, **kwargs):
    """Keep the review aggregate aligned with its authoritative durable job."""

    from .issue_draft_publication_state import project_publication_job_terminal

    project_publication_job_terminal(instance)


@receiver(ecr_publication_completed)
def track_completed_ecr_publication(sender, *, owner, issue, title, projects, **kwargs):
    """Create the watcher within the ECR publication completion transaction."""

    from .record_services import track_published_issue

    track_published_issue(owner, issue, title, projects)
