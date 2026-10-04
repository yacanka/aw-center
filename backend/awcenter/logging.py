"""Small dependency-free JSON logging primitives for production events."""

import json
import logging
from datetime import UTC, datetime


def exception_log_context(exception_type, traceback):
    """Return bounded exception metadata without retaining the exception or frames."""

    context = {"exception_type": exception_type.__name__}
    if traceback is None:
        return context
    # The innermost frame identifies the failure without messages, local values,
    # source text, or absolute filesystem paths.
    while traceback.tb_next is not None:
        traceback = traceback.tb_next
    module = traceback.tb_frame.f_globals.get("__name__")
    context["exception_location"] = {
        "module": module if isinstance(module, str) else "<unknown>",
        "function": traceback.tb_frame.f_code.co_name,
        "line": traceback.tb_lineno,
    }
    return context


def _declared_exception_context(record):
    """Project only scalar metadata from a record without raw exception info."""

    context = {}
    exception_type = getattr(record, "exception_type", None)
    if isinstance(exception_type, str):
        context["exception_type"] = exception_type
    location = getattr(record, "exception_location", None)
    if not isinstance(location, dict):
        return context
    module, function, line = (location.get(name) for name in ("module", "function", "line"))
    if isinstance(module, str) and isinstance(function, str) and type(line) is int:
        context["exception_location"] = {"module": module, "function": function, "line": line}
    return context


class JsonEventFormatter(logging.Formatter):
    """Serialize declared context while excluding payload and credential data."""

    def format(self, record):
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "request_id": getattr(record, "request_id", "-"),
        }
        for name in (
            "user_id",
            "method",
            "path",
            "status",
            "duration_ms",
            "job_id",
            "job_kind",
            "attempt",
            "terminal_code",
            "worker_id",
            "execution_id",
            "error_type",
            "failure_stage",
            "delivery_id",
            "notification_id",
        ):
            value = getattr(record, name, None)
            if value is not None:
                event[name] = value
        if record.exc_info:
            event.update(exception_log_context(record.exc_info[0], record.exc_info[2]))
        else:
            event.update(_declared_exception_context(record))
        return json.dumps(event, ensure_ascii=True, separators=(",", ":"), default=str)
