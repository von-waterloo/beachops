"""Structured JSON logging without prompts, code, or credentials."""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator

from beachops.services.redaction import redact_text

_EXTRA_FIELDS = (
    "correlation_id",
    "job_id",
    "run_id",
    "user_id",
    "action",
    "service",
    "duration_ms",
    "error_code",
)

_log_context: ContextVar[dict[str, Any]] = ContextVar("beachops_log_context", default={})

_BOT_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])\d{8,12}:[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_-])")


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def get_log_context() -> dict[str, Any]:
    return dict(_log_context.get())


def bind_log_context(**kwargs: Any) -> None:
    """Merge fields into the current context (skip None values)."""
    current = dict(_log_context.get())
    for key, value in kwargs.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    _log_context.set(current)


def clear_log_context() -> None:
    _log_context.set({})


@contextmanager
def log_context(**kwargs: Any) -> Iterator[None]:
    """Temporarily bind context fields, restoring previous state on exit."""
    token = _log_context.set({**_log_context.get(), **{k: v for k, v in kwargs.items() if v is not None}})
    try:
        yield
    finally:
        _log_context.reset(token)


def _redact_log_text(value: str) -> str:
    redacted = redact_text(value)
    return _BOT_TOKEN_RE.sub("[REDACTED]", redacted)


class ContextFilter(logging.Filter):
    """Copy contextvars onto LogRecord for JsonFormatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in _log_context.get().items():
            if value is not None and not hasattr(record, key):
                setattr(record, key, value)
        return True


class RedactionFilter(logging.Filter):
    """Mask secrets that may leak into message or exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_log_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: _redact_log_text(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact_log_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = _redact_log_text(record.getMessage())
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = _redact_log_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_logging(level: str, *, service: str | None = None) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # These clients may include sensitive URLs or auth metadata.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    if service:
        bind_log_context(service=service)
