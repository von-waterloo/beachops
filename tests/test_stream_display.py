"""Tests for stream thinking visibility policy."""

from __future__ import annotations

from beachops.domain.models import UserMode
from beachops.services.stream_display import resolve_thinking_display


def test_preview_mode_ask_is_count() -> None:
    assert (
        resolve_thinking_display("preview", UserMode.ASK, is_admin=False)
        == "count"
    )


def test_preview_mode_plan_is_preview() -> None:
    assert (
        resolve_thinking_display("preview", UserMode.PLAN, is_admin=False)
        == "preview"
    )


def test_admin_mode_non_admin_plan_is_none() -> None:
    assert (
        resolve_thinking_display("admin", UserMode.PLAN, is_admin=False)
        == "none"
    )


def test_admin_mode_admin_plan_is_preview() -> None:
    assert (
        resolve_thinking_display("admin", UserMode.PLAN, is_admin=True)
        == "preview"
    )


def test_off_mode_is_none() -> None:
    assert resolve_thinking_display("off", UserMode.DO, is_admin=True) == "none"
