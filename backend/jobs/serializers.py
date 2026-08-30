from django.urls import reverse
from rest_framework import serializers

from .models import Job, JobEvent, JobStatus
from .recovery import recovery_hint


class JobEventSerializer(serializers.ModelSerializer):
    """Serialize immutable job audit events."""

    class Meta:
        model = JobEvent
        fields = ["id", "status", "progress", "message", "code", "details", "created_at"]


class JobSerializer(serializers.ModelSerializer):
    """Serialize safe job state without storage paths or private parameters."""

    can_cancel = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    recovery_hint = serializers.SerializerMethodField()
    jira_draft = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "kind", "title", "status", "progress", "message", "error_code",
            "input_name", "output_name", "result_summary", "attempt", "max_attempts",
            "source_job", "workflow_run", "workflow_step",
            "request_id",
            "created_at", "started_at", "completed_at", "confirmation_expires_at", "updated_at",
            "can_cancel", "download_url", "recovery_hint", "jira_draft",
        ]

    def get_can_cancel(self, job):
        """Return whether the current state accepts cancellation."""

        return job.status in {JobStatus.QUEUED, JobStatus.RUNNING}

    def get_download_url(self, job):
        """Return an owned API URL only when output is available."""

        if job.status != JobStatus.SUCCEEDED or not job.output_file:
            return None
        return reverse("job_download", kwargs={"job_id": job.id})

    def get_recovery_hint(self, job):
        """Return an actionable sanitized hint for failed jobs."""

        if job.status not in {
            JobStatus.FAILED,
            JobStatus.RECONCILIATION_REQUIRED,
        }:
            return ""
        return recovery_hint(job.error_code)

    def get_jira_draft(self, job):
        """Return a content-free reference to an existing analysis review draft."""

        draft = getattr(job, "jira_issue_draft", None)
        if draft is None:
            return None
        return {
            "id": str(draft.id), "status": draft.status,
            "version": draft.version, "jira_issue_key": draft.jira_issue_key,
        }


class JobDetailSerializer(JobSerializer):
    """Serialize job state together with its bounded audit history."""

    events = serializers.SerializerMethodField()

    class Meta(JobSerializer.Meta):
        fields = [*JobSerializer.Meta.fields, "events"]

    def get_events(self, job):
        """Return at most the newest one hundred events in chronological order."""

        events = list(job.events.order_by("-created_at", "-id")[:100])
        return JobEventSerializer(reversed(events), many=True).data
