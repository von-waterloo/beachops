"""Tests for markdown sanitization before Telegram conversion."""

from __future__ import annotations

from tg_cursor_bot.services.markdown_sanitize import (
    make_telegram_safe_markdown,
    readable_plain,
    strip_poison_markdown,
)


def test_cursor_fence_normalized():
    raw = "```43:54:frontend/src/components/agent/SelectionHandler.jsx\n      if (x) {\n```"
    out = make_telegram_safe_markdown(raw)
    assert "43:54:" not in out
    assert "// frontend/src/components/agent/SelectionHandler.jsx" in out
    assert out.count("```") % 2 == 0


def test_autolink_angle_brackets_to_backticks():
    raw = "<frontend/src/context/agentcontext.jsx>"
    out = make_telegram_safe_markdown(raw)
    assert "<frontend" not in out
    assert "`frontend/src/context/agentcontext.jsx`" in out


def test_relative_link_to_backticks():
    raw = "[`File.jsx`](frontend/src/components/File.jsx)"
    out = make_telegram_safe_markdown(raw)
    assert "](frontend" not in out
    assert "`" in out


def test_unclosed_fence_closed():
    raw = "text\n```python\nprint(1)"
    out = make_telegram_safe_markdown(raw)
    assert out.count("```") % 2 == 0


def test_readable_plain_strips_headings_and_bold():
    raw = "## Title\n\n**bold** text"
    out = readable_plain(raw)
    assert "##" not in out
    assert "**" not in out
    assert "Title" in out
    assert "bold" in out


def test_strip_poison_flattens_table_rows():
    raw = "| A | B |\n|---|---|\n| 1 | 2 |"
    out = strip_poison_markdown(raw)
    assert "|---|" not in out
