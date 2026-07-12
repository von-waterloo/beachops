"""Tests for ui_copy helpers."""

from __future__ import annotations

from beachops.domain.models import UserMode
from beachops.services.ui_copy import (
    build_welcome_message,
    cancel_ok,
    queued_message,
    queue_full_message,
)


def test_welcome_message_contains_quick_start() -> None:
    text = build_welcome_message(
        mode=UserMode.ASK,
        model_key="composer-2.5",
        repo=None,
        is_admin=False,
        has_repos=False,
    )
    assert "/repo" in text
    assert "/ask" in text


def test_queued_message_position() -> None:
    assert "#2" in queued_message(2)


def test_cancel_ok_with_queue() -> None:
    assert "2" in cancel_ok(cleared_queue=2)


def test_queue_full_message() -> None:
    assert "/cancel" in queue_full_message()
