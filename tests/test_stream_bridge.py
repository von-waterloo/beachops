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


def test_merge_stream_chunk_delta_and_cumulative() -> None:
    from beachops.services.stream_bridge import merge_stream_chunk

    assert merge_stream_chunk("", "И") == "И"
    assert merge_stream_chunk("И", "щ") == "Ищ"
    assert merge_stream_chunk("Ищ", "Ищу") == "Ищу"
    assert merge_stream_chunk("Ищу", "Ищ") == "Ищу"
    assert merge_stream_chunk("Ищу", "Ищу") == "Ищу"


def test_append_assistant_ignores_cumulative_replay() -> None:
    state = StreamState()
    state.append_assistant("И")
    state.append_assistant("щ")
    state.append_assistant("у")
    assert state.assistant_text == "Ищу"
    # Cumulative snapshot must replace, not double.
    state.append_assistant("Ищу UI")
    assert state.assistant_text == "Ищу UI"
    # Exact duplicate must not grow.
    state.append_assistant("Ищу UI")
    assert state.assistant_text == "Ищу UI"


def test_append_thinking_tracks_growth_without_doubling() -> None:
    state = StreamState()
    state.append_thinking("ab")
    state.append_thinking("cd")
    assert state.thinking_text == "abcd"
    assert state.thinking_chars == 4
    state.append_thinking("abcd")  # cumulative replay
    assert state.thinking_text == "abcd"
    assert state.thinking_chars == 4
