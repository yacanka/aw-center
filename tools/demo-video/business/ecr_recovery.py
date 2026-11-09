"""Stage an isolated interrupted ECR write, then honor cancellation with the real job kernel."""
import argparse
import json
from pathlib import Path
from uuid import UUID, uuid4

from prepare_scene import prepare

WORKER = "atlas-video:ecr-cancellation"


def stage(project, owner, sample):
    from automations.ecr_publication_executor import attachment_filename
    from automations.ecr_publication_jobs import JOB_KIND, enqueue_ecr_publication
    from automations.ecr_services import approve_ecr_workflow, create_ecr_workflow
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import transaction
    from jobs.worker import claim_next_job
    from jira_demo import LocalJira

    upload = SimpleUploadedFile(sample.name, sample.read_bytes(), content_type="application/pdf")
    key = f"video-ecr-recovery-{uuid4().hex}"
    with transaction.atomic():
        workflow, _ = create_ecr_workflow(owner, [project], upload, key)
        workflow = approve_ecr_workflow(workflow.id, owner, {"version": workflow.version, "project_key": "DEMO"})
        workflow, job, _ = enqueue_ecr_publication(owner, workflow.id, workflow.version, key, action="publish")
        claimed = claim_next_job(WORKER, [JOB_KIND])
        if not claimed or claimed.pk != job.pk:
            raise RuntimeError("Another ECR publication is queued; retry this fixture when it finishes.")
    # The fake transport accepted the write, but the original worker has not received its reply.
    client = LocalJira()
    issue = client.create_issue({"summary": workflow.snapshot["title"], "labels": [workflow.marker_label]})
    with sample.open("rb") as stream:
        client.add_attachment(issue.key, stream, attachment_filename(workflow))
    return {"workflow": str(workflow.id), "job": str(job.id), "issue": issue.key}


def honor_cancellation(project, owner, job_id):
    from automations.models import EcrWorkflow
    from jobs.contracts import JobCancelled
    from jobs.execution import cancellation_requested, remove_worker
    from jobs.models import JobStatus
    from jobs.worker import execute_claimed_job

    workflow = EcrWorkflow.objects.get(projects=project, owner=owner, publication_job_id=job_id)
    job = workflow.publication_job
    if job.worker_id != WORKER or job.status != JobStatus.CANCEL_REQUESTED:
        raise RuntimeError("A cancellation of the staged ECR job is required.")

    def interrupted_provider(active_job):
        if not cancellation_requested(active_job.id):
            raise RuntimeError("Cancellation intent disappeared.")
        raise JobCancelled()

    try:
        execute_claimed_job(job, lambda kind: interrupted_provider)
    finally:
        remove_worker(WORKER)
    job.refresh_from_db()
    if job.status != JobStatus.RECONCILIATION_REQUIRED:
        raise RuntimeError("The interrupted external write did not request reconciliation.")
    return {"state": job.status}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "cancel"])
    parser.add_argument("job", type=UUID, nargs="?")
    args = parser.parse_args()
    generation = prepare(False)
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from orgs.models import Project
    from run import STATE

    if Path(settings.DATABASES["default"]["NAME"]).resolve() != generation / "demo.sqlite3":
        raise RuntimeError("ECR recovery needs the isolated video database.")
    project = Project.objects.get(slug="gokbey", name="Atlas Demo Projesi")
    owner = get_user_model().objects.get(username="D10001")
    if args.action == "stage":
        result = stage(project, owner, STATE / "examples/ECD-101.pdf")
    else:
        result = honor_cancellation(project, owner, args.job)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
