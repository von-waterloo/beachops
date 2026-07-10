"""Tests for Telegram markdown formatting pipeline."""

from __future__ import annotations

from telegramify_markdown import utf16_len

from beachops.services.markdown_format import (
    format_markdown_message,
    format_readable_message,
)

_PREFIX = "Режим · чат\nРепо · test"
_SUFFIX = "⏱ 10 сек"


def test_simple_bold_returns_entities():
    result = format_markdown_message(_PREFIX, "**hello**", _SUFFIX)
    assert result is not None
    text, entities = result
    assert entities is not None
    assert len(entities) > 0
    assert any(e.type == "bold" for e in entities)
    assert "**" not in text


def test_cursor_style_body_formats_or_readable():
    body = """## Точная причина

**Это не перезагрузка.**

```43:54:frontend/src/foo.jsx
const x = 1;
```

| Симптом | Причина |
|---|---|
| Спиннер | switchChat |

[`File.jsx`](frontend/src/x)
"""
    result = format_markdown_message(_PREFIX, body, _SUFFIX)
    assert result is not None
    text, entities = result
    assert _PREFIX in text
    assert _SUFFIX in text
    assert "##" not in text
    assert "**" not in text
    if entities is None:
        assert "Точная причина" in text
    else:
        assert len(entities) > 0


def test_format_never_returns_none_for_nonempty_body():
    body = "## x\n\n**y**"
    result = format_markdown_message(_PREFIX, body, "")
    assert result is not None


def test_empty_body_returns_none():
    assert format_markdown_message(_PREFIX, "   ", _SUFFIX) is None


def test_readable_message_strips_markdown():
    text = format_readable_message(_PREFIX, "## Hi\n\n**there**", _SUFFIX)
    assert "##" not in text
    assert "**" not in text
    assert "Hi" in text
    assert "there" in text


def test_relative_links_stripped_from_entities():
    """Even if convert emits text_link, invalid http URLs must not be sent."""
    body = "[`AgentContext.jsx`](frontend/src/context/agentcontext.jsx)"
    result = format_markdown_message(_PREFIX, body, "")
    assert result is not None
    _text, entities = result
    if entities:
        for ent in entities:
            if ent.type == "text_link" and ent.url:
                assert ent.url.startswith(("http://", "https://"))


def test_long_body_within_telegram_limit():
    body = "## Section\n\n" + ("paragraph line.\n\n" * 400)
    result = format_markdown_message(_PREFIX, body, _SUFFIX)
    assert result is not None
    text, _entities = result
    assert utf16_len(text) <= 4096
