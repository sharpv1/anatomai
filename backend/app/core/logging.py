import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_EVENTS = {
    "http_request",
    "request_failed",
    "readiness_failed",
    "import_processing_failed",
    "import_job_finished",
}
_SAFE_FIELDS = ("method", "route", "status", "duration_ms", "error_type", "code", "job_id")


class JsonFormatter(logging.Formatter):
    """Allowlisted structured fields, never arbitrary messages, inputs or tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": message if message in _EVENTS else "library_log",
        }
        if request_id := request_id_context.get():
            payload["request_id"] = request_id
        for name in _SAFE_FIELDS:
            if name in record.__dict__:
                payload[name] = record.__dict__[name]
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
