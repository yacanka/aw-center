"""Serialize development reset preparation with incoming compliance writes."""

from contextlib import contextmanager
from functools import wraps

from django.conf import settings
from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import APIException

from .models import DeveloperResetState


class ResetInProgress(APIException):
    status_code = 409
    default_code = "COMPLIANCE_RESET_IN_PROGRESS"
    default_detail = "Test data reset is being prepared. Release preparation in Developer / Test Data to resume writes."


def reset_enabled():
    return settings.DEBUG and settings.AWCENTER_DEPLOYMENT_MODE == "development"


@contextmanager
def lock_reset_state():
    """Acquire the same database fence for reset and writers, including SQLite.

    The UPDATE acquires SQLite's write lock before any read; select_for_update
    alone would not serialize it. Production does not consult this dev state.
    """
    if not reset_enabled():
        yield None
        return
    with transaction.atomic():
        DeveloperResetState.objects.filter(pk=1).update(active=F("active"))
        DeveloperResetState.objects.get_or_create(pk=1)
        yield DeveloperResetState.objects.select_for_update().get(pk=1)


def reset_sensitive_write(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with lock_reset_state() as state:
            if state and state.active:
                raise ResetInProgress()
            return function(*args, **kwargs)
    return guarded
