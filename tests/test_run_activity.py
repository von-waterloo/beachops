"""Tests for run activity line helpers."""

from __future__ import annotations

from tg_cursor_bot.services.status_animation import format_run_activity_line, run_activity_frame


def test_run_activity_frame_cycles() -> None:
    assert run_activity_frame(0) == "◐"
    assert run_activity_frame(4) == "◐"
    assert run_activity_frame(1) == "◓"


def test_format_run_activity_line_with_elapsed() -> None:
    text = format_run_activity_line("◑", elapsed_sec=12)
    assert "💭 Агент работает  ◑" in text
    assert "⏱ 12 сек" in text
