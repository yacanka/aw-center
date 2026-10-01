"""Project-scoped status options and the fence shared by assignments and deletion."""
import re
from contextlib import contextmanager

from django.db import transaction
from django.db.models import Count, F
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, ValidationError

from orgs.models import Project
from .models import ComplianceDocument, DocumentStatus


class StatusConflict(APIException):
    status_code = 409
    default_code = "COMPLIANCE_STATUS_CONFLICT"
    default_detail = "This status is in use or already exists."


def normalize_status(value):
    """Use the legacy import spelling, without restricting project vocabulary."""
    if value is None or isinstance(value, str) and not value.strip():
        return "unknown", "Unknown"
    if not isinstance(value, str) or re.search(r"[\x00-\x1f\x7f]", value):
        raise ValidationError({"status": "Use a single-line status name."})
    label = re.sub(r"\s+", " ", value.strip())
    code = re.sub(r"\s+", "_", label.casefold().replace(".", ""))
    if not code or len(code) > 128 or len(label) > 128:
        raise ValidationError({"status": "Use a status name with at most 128 characters."})
    if code == "delayed":
        raise ValidationError({"status": "Delayed is calculated, not an assignable status."})
    return code, "Unknown" if code == "unknown" else label


@contextmanager
def lock_status_project(project):
    """UPDATE first also serializes SQLite, where FOR UPDATE is ineffective.

    Acquire before document locks, on every catalog/assignment write path.
    This is a no-op on project data and does not produce business history.
    """
    with transaction.atomic():
        Project.objects.filter(pk=project.pk).update(enabled=F("enabled"))
        yield


def ensure_status(project, value, label):
    return DocumentStatus.objects.get_or_create(
        project=project, value=value, defaults={"label": label},
    )[0]


def status_options(project):
    counts = dict(ComplianceDocument.objects.filter(project=project).values("status").annotate(
        total=Count("id")
    ).values_list("status", "total"))
    return [status_payload(item, counts.get(item.value, 0)) for item in
            DocumentStatus.objects.filter(project=project).order_by("label", "value")]


def status_payload(item, count=0):
    return {"id": str(item.pk), "value": item.value, "label": item.label,
            "usage_count": count, "can_delete": item.value != "unknown" and count == 0}


def create_status(project, label):
    if not isinstance(label, str) or not label.strip():
        raise ValidationError({"label": "A status name is required."})
    value, label = normalize_status(label)
    with lock_status_project(project):
        if DocumentStatus.objects.filter(project=project, value=value).exists():
            raise StatusConflict("This project already has that status.")
        return DocumentStatus.objects.create(project=project, value=value, label=label)


def delete_status(project, status_id):
    with lock_status_project(project):
        item = get_object_or_404(DocumentStatus, project=project, pk=status_id)
        if item.value == "unknown" or ComplianceDocument.objects.filter(project=project, status=item.value).exists():
            raise StatusConflict("Default or currently used statuses cannot be deleted.")
        item.delete()
