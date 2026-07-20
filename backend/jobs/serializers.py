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
    can_retry = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    recovery_hint = serializers.SerializerMethodField()
    handoffs = serializers.SerializerMethodField()
    jira_draft = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "kind", "title", "status", "progress", "message", "error_code",
            "input_name", "output_name", "result_summary", "attempt", "max_attempts",
            "retry_of", "source_job", "workflow_run", "workflow_step", "retryable",
            "request_id",
            "created_at", "started_at", "completed_at", "confirmation_expires_at", "updated_at",
            "can_cancel", "can_retry", "download_url", "recovery_hint", "handoffs", "jira_draft",
        ]

    def get_can_cancel(self, job):
        """Return whether the current state accepts cancellation."""

        return job.status in {JobStatus.QUEUED, JobStatus.RUNNING}

    def get_can_retry(self, job):
        """Return whether retry policy permits a new attempt."""

        return (
            job.status in {JobStatus.FAILED, JobStatus.CANCELLED}
            and job.retryable
            and job.attempt < job.max_attempts
        )

    def get_download_url(self, job):
        """Return an owned API URL only when output is available."""

        return f"/jobs/{job.id}/download/" if job.status == JobStatus.SUCCEEDED and job.output_file else None

    def get_recovery_hint(self, job):
        """Return an actionable sanitized hint for failed jobs."""

        return recovery_hint(job.error_code) if job.status == JobStatus.FAILED else ""

    def get_handoffs(self, job):
        """Return allowlisted next actions for a verified completed output."""

        from .handoffs import available_handoffs

        return available_handoffs(job)

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
