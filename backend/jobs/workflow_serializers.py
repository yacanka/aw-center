"""Safe API serializers for workflow recipes and runs."""

from rest_framework import serializers

from .recovery import recovery_hint
from .serializers import JobSerializer
from .workflow_models import WorkflowRun, WorkflowRunEvent, WorkflowStatus
from .workflow_recipes import WORKFLOW_RECIPES


class WorkflowEventSerializer(serializers.ModelSerializer):
    """Serialize one immutable workflow transition."""

    class Meta:
        model = WorkflowRunEvent
        fields = ["id", "status", "step", "message", "code", "details", "created_at"]


class WorkflowRunSerializer(serializers.ModelSerializer):
    """Serialize a workflow with its latest job attempt for each recipe step."""

    progress = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    recovery_hint = serializers.SerializerMethodField()
    steps = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowRun
        fields = [
            "id", "recipe", "title", "status", "progress", "message", "error_code",
            "input_name", "current_step", "total_steps", "request_id", "can_cancel",
            "recovery_hint",
            "steps", "created_at", "completed_at", "updated_at",
        ]

    def get_progress(self, workflow):
        """Calculate overall progress from completed steps and the active job."""

        jobs = latest_jobs_by_step(workflow)
        current = jobs.get(workflow.current_step)
        completed = max(0, workflow.current_step - 1)
        current_progress = current.progress if current else 0
        if workflow.status == WorkflowStatus.SUCCEEDED:
            return 100
        return min(99, int(((completed + current_progress / 100) / workflow.total_steps) * 100))

    def get_can_cancel(self, workflow):
        """Return whether the workflow still accepts cancellation."""

        return workflow.status in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}

    def get_recovery_hint(self, workflow):
        """Return one actionable next step for failed workflow state."""

        return recovery_hint(workflow.error_code) if workflow.status == WorkflowStatus.FAILED else ""

    def get_steps(self, workflow):
        """Return recipe steps paired with their latest durable job attempts."""

        recipe = WORKFLOW_RECIPES.get(workflow.recipe)
        if not recipe:
            return []
        jobs = latest_jobs_by_step(workflow)
        return [
            {
                "sequence": step.sequence,
                "kind": step.kind,
                "label": step.label,
                "job": JobSerializer(jobs[step.sequence]).data if step.sequence in jobs else None,
            }
            for step in recipe.steps
        ]


class WorkflowRunDetailSerializer(WorkflowRunSerializer):
    """Serialize a workflow run with bounded audit history."""

    events = serializers.SerializerMethodField()

    class Meta(WorkflowRunSerializer.Meta):
        fields = [*WorkflowRunSerializer.Meta.fields, "events"]

    def get_events(self, workflow):
        """Return at most one hundred newest workflow events chronologically."""

        events = list(workflow.events.order_by("-created_at", "-id")[:100])
        return WorkflowEventSerializer(reversed(events), many=True).data


def latest_jobs_by_step(workflow):
    """Index the newest job attempt for each workflow sequence."""

    latest = {}
    jobs = sorted(workflow.jobs.all(), key=lambda job: (job.workflow_step or 0, job.attempt))
    for job in jobs:
        latest[job.workflow_step] = job
    return latest
