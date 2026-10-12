"""Bounded retries for the small user preference/content write surfaces."""

import sqlite3
import time

from django.db import OperationalError, connection, transaction
from rest_framework.exceptions import APIException


class ContentConflict(APIException):
    status_code = 409

    def __init__(self, code):
        super().__init__({"detail": "The saved data changed. Reload and retry.", "code": code})


class ContentStorageBusy(APIException):
    status_code = 503
    default_detail = "Storage is busy. Retry the operation."
    default_code = "CONTENT_STORAGE_BUSY"


def retry_content_write(operation, *, conflict_code):
    """Run up to three fresh transactions; None denotes a failed version CAS.

    Only SQLite's driver-reported busy/locked errors are retryable here. Other
    database failures must retain their ordinary error handling.
    """
    for attempt in range(3):
        try:
            with transaction.atomic():
                result = operation()
            if result is not None:
                return result
        except OperationalError as error:
            code = getattr(error.__cause__, "sqlite_errorcode", None)
            if connection.vendor != "sqlite" or not isinstance(code, int) or code & 255 not in (
                sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED
            ):
                raise
            if attempt == 2:
                raise ContentStorageBusy() from error
        if attempt < 2:
            time.sleep(0.02 * (attempt + 1))
    raise ContentConflict(conflict_code)
