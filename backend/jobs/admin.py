from django.contrib import admin

from .models import Job, JobEvent, WorkerHeartbeat


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
        "retry_of", "request_id", "worker_id", "lease_expires_at", "cancel_requested_at",
        "started_at", "completed_at", "created_at", "updated_at",
    ]
    inlines = [JobEventInline]


@admin.register(WorkerHeartbeat)
class WorkerHeartbeatAdmin(admin.ModelAdmin):
    """Expose worker heartbeat freshness to administrators."""

    list_display = ["worker_id", "current_job", "started_at", "heartbeat_at"]
    readonly_fields = ["worker_id", "current_job", "started_at", "heartbeat_at"]
