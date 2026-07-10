"""Tests for StreamState rendering."""

from __future__ import annotations

from beachops.services.stream_bridge import StreamState
from beachops.services.ui_copy import EMPTY_STREAM_HINT, format_tool_line


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
    assert "читаю файл" in format_tool_line("read_file", "running")
    assert "✅" in format_tool_line("grep", "completed")
    # Unknown tools keep their raw name.
    assert "grep" in format_tool_line("grep", "completed")


def test_tool_line_upsert_replaces_status_for_ru_label() -> None:
    state = StreamState()
    state.upsert_tool("read_file", "running")
    state.upsert_tool("read_file", "completed")
    assert len(state.tool_lines) == 1
    assert "✅" in state.tool_lines[0]


def test_set_plan_stores_text_and_name() -> None:
    state = StreamState()
    state.set_plan("# План\n\nШаги", name="Мой план")
    assert state.plan_text == "# План\n\nШаги"
    assert state.plan_name == "Мой план"
    state.set_plan("   ")
    assert state.plan_text is None


def test_empty_stream_hint() -> None:
    state = StreamState()
    assert state.render_body() == EMPTY_STREAM_HINT
