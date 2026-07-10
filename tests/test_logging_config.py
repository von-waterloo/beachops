"""Tests for structured JSON logging."""

from __future__ import annotations

import json
import logging

from beachops.services.logging_config import (
    ContextFilter,
    JsonFormatter,
    RedactionFilter,
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_log_context,
    log_context,
    new_correlation_id,
)


def test_json_formatter_includes_context_and_redacts_secrets() -> None:
    clear_log_context()
    configure_logging("INFO", service="test")
    bind_log_context(user_id=42, action="unit")

    record = logging.LogRecord(
        name="beachops.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token sk-abcdefghijklmnopqrstuvwxyz012345 and ok",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-1"
    record.duration_ms = 12
    ContextFilter().filter(record)
    RedactionFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["service"] == "test"
    assert payload["user_id"] == 42
    assert payload["action"] == "unit"
    assert payload["job_id"] == "job-1"
    assert payload["duration_ms"] == 12
    assert "sk-" not in payload["message"]
    assert "[REDACTED]" in payload["message"]
    clear_log_context()


def test_log_context_restores_previous() -> None:
    clear_log_context()
    bind_log_context(service="outer", user_id=1)
    with log_context(user_id=2, action="inner"):
        ctx = get_log_context()
        assert ctx["user_id"] == 2
        assert ctx["action"] == "inner"
        assert ctx["service"] == "outer"
    assert get_log_context()["user_id"] == 1
    assert "action" not in get_log_context()
    clear_log_context()


def test_new_correlation_id_is_short_hex() -> None:
    value = new_correlation_id()
    assert len(value) == 16
    int(value, 16)
