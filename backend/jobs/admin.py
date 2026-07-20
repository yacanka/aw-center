from django.contrib import admin

from .models import Job, JobEvent, WorkerHeartbeat, WorkflowRun, WorkflowRunEvent


class JobEventInline(admin.TabularInline):
    """Display immutable job events inside admin job details."""

    model = JobEvent
    extra = 0
    can_delete = False
    readonly_fields = ["status", "progress", "message", "code", "details", "created_at"]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Expose safe operational job state to administrators."""

    list_display = ["id", "kind", "owner", "status", "progress", "attempt", "created_at"]
    list_filter = ["kind", "status", "created_at"]
    search_fields = ["id", "title", "owner__username", "input_name", "error_code"]
    readonly_fields = [
        "id", "owner", "kind", "title", "status", "progress", "message", "parameters",
        "input_file", "input_name", "input_sha256", "output_file", "output_name",
        "output_sha256", "result_summary", "error_code", "idempotency_key", "attempt", "max_attempts",
        "retryable",
        "retry_of", "source_job", "workflow_run", "workflow_step", "request_id",
        "worker_id", "lease_expires_at", "confirmation_expires_at", "cancel_requested_at",
        "started_at", "completed_at", "created_at", "updated_at",
    ]
    inlines = [JobEventInline]


@admin.register(WorkerHeartbeat)
class WorkerHeartbeatAdmin(admin.ModelAdmin):
    """Expose worker heartbeat freshness to administrators."""

    list_display = ["worker_id", "current_job", "started_at", "heartbeat_at"]
    readonly_fields = ["worker_id", "current_job", "started_at", "heartbeat_at"]


class WorkflowRunEventInline(admin.TabularInline):
    """Display immutable workflow events inside admin run details."""

    model = WorkflowRunEvent
    extra = 0
    can_delete = False
    readonly_fields = ["status", "step", "message", "code", "details", "created_at"]


@admin.register(WorkflowRun)
class WorkflowRunAdmin(admin.ModelAdmin):
    """Expose safe workflow state and provenance to administrators."""

    list_display = ["id", "recipe", "owner", "status", "current_step", "created_at"]
    list_filter = ["recipe", "status", "created_at"]
    search_fields = ["id", "title", "owner__username", "input_name", "error_code"]
    readonly_fields = [
        "id", "owner", "recipe", "title", "status", "parameters", "input_name",
        "input_sha256", "current_step", "total_steps", "message", "error_code",
        "idempotency_key", "request_id", "completed_at", "created_at", "updated_at",
    ]
    inlines = [WorkflowRunEventInline]
