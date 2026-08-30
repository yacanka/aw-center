"""Transactional DCC record mutations with optimistic concurrency."""

from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import APIException

from .access_policy import OPERATOR, require_projects_role, require_resource_role
from .models import DccRecord


class DccRecordVersionConflict(APIException):
    status_code = 409
    default_code = "DCC_RECORD_VERSION_CONFLICT"
    default_detail = "The DCC record changed. Refresh it before continuing."


def create_record(actor, values):
    projects = list(values.pop("projects"))
    assigned_users = list(values.pop("assigned_users", ()))
    require_projects_role(actor, projects, OPERATOR)
    with transaction.atomic():
        record = DccRecord.objects.create(owner=actor, **values)
        record.projects.set(projects)
        record.assigned_users.set(assigned_users)
    return record


def update_record(record_id, actor, values):
    expected_version = values.pop("version")
    with transaction.atomic():
        record = locked_record(record_id)
        require_resource_role(actor, record, OPERATOR)
        if record.version != expected_version:
            raise DccRecordVersionConflict()
        projects = list(values.pop("projects", record.projects.all()))
        require_projects_role(actor, projects, OPERATOR)
        assigned_users = values.pop("assigned_users", None)
        for field, value in values.items():
            setattr(record, field, value)
        record.version += 1
        record.save()
        record.projects.set(projects)
        if assigned_users is not None:
            record.assigned_users.set(assigned_users)
    return record


def delete_record(record_id, actor, expected_version):
    with transaction.atomic():
        record = locked_record(record_id)
        require_resource_role(actor, record, OPERATOR)
        if record.version != expected_version:
            raise DccRecordVersionConflict()
        record.delete()


def locked_record(record_id):
    try:
        return DccRecord.objects.select_for_update().get(pk=record_id)
    except DccRecord.DoesNotExist as error:
        raise Http404 from error
