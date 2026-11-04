"""A monotonic deadline shared by nested probes in one discovery operation."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
import time

_deadline = ContextVar('awcenter_probe_deadline', default=None)


@contextmanager
def deadline_at(value):
    token = _deadline.set(value)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining(cap, error_type):
    deadline = _deadline.get()
    seconds = cap if deadline is None else min(cap, deadline - time.monotonic())
    if seconds <= 0:
        raise error_type('timeout')
    return seconds


def bounded(seconds, error_type):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            if _deadline.get() is not None:
                return function(*args, **kwargs)
            token = _deadline.set(time.monotonic() + seconds)
            try:
                return function(*args, **kwargs)
            finally:
                _deadline.reset(token)
        return run
    return decorate
