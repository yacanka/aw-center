"""Durable models for owner-scoped multi-step workflows."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class WorkflowStatus(models.TextChoices):
    """Describe the lifecycle of one workflow run."""

    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    CANCEL_REQUESTED = "cancel_requested", "Cancel requested"
    CANCELLED = "cancelled", "Cancelled"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class WorkflowRun(models.Model):
    """Represent one durable execution of an allowlisted workflow recipe."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workflow_runs"
    )
    recipe = models.CharField(max_length=64)
    title = models.CharField(max_length=160)
    status = models.CharField(
        max_length=24, choices=WorkflowStatus.choices, default=WorkflowStatus.QUEUED
    )
    parameters = models.JSONField(default=dict, blank=True)
    input_name = models.CharField(max_length=180)
    input_sha256 = models.CharField(max_length=64)
    current_step = models.PositiveSmallIntegerField(default=1)
    total_steps = models.PositiveSmallIntegerField()
    message = models.CharField(max_length=500, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "updated_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "recipe", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="jobs_unique_owner_recipe_idempotency",
            )
        ]


class WorkflowRunEvent(models.Model):
    """Record an immutable sanitized workflow transition."""

    workflow = models.ForeignKey(WorkflowRun, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=24, choices=WorkflowStatus.choices)
    step = models.PositiveSmallIntegerField(default=1)
    message = models.CharField(max_length=500)
    code = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
