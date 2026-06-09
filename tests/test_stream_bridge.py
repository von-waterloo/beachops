"""Tests for StreamState rendering."""

from __future__ import annotations

from tg_cursor_bot.services.stream_bridge import StreamState
from tg_cursor_bot.services.ui_copy import EMPTY_STREAM_HINT, format_tool_line


def test_thinking_count_visible() -> None:
    state = StreamState()
    state.append_thinking("internal reasoning")
    assert state.has_visible_output(thinking_display="count")
    assert "Думаю" in state.render_body(thinking_display="count")


def test_thinking_preview_visible() -> None:
    state = StreamState()
    state.append_thinking("internal reasoning")
    assert state.has_visible_output(thinking_display="preview")
    body = state.render_body(thinking_display="preview", preview_max=50)
    assert "reasoning" in body


def test_thinking_hidden_when_assistant_started() -> None:
    state = StreamState()
    state.append_thinking("secret thoughts")
    state.append_assistant("Answer")
    body = state.render_body(thinking_display="preview")
    assert "secret" not in body
    assert "Answer" in body


def test_assistant_visible_output() -> None:
    state = StreamState()
    state.append_assistant("Hello")
    assert state.has_visible_output()
    assert "Hello" in state.render_body()


def test_tool_line_format() -> None:
    assert "read_file" in format_tool_line("read_file", "running")
    assert "✅" in format_tool_line("grep", "completed")


def test_empty_stream_hint() -> None:
    state = StreamState()
    assert state.render_body() == EMPTY_STREAM_HINT
