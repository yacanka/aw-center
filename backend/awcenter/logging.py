"""Small dependency-free JSON logging primitives for production events."""

import json
import logging
from datetime import UTC, datetime


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
        ):
            value = getattr(record, name, None)
            if value is not None:
                event[name] = value
        if record.exc_info:
            event["exception_type"] = record.exc_info[0].__name__
        return json.dumps(event, ensure_ascii=True, separators=(",", ":"), default=str)
