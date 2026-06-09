"""Tests for forward message formatting."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from telegram import (
    Chat,
    Message,
    MessageOriginUser,
    User,
)

from tg_cursor_bot.services.forward_format import (
    format_forward_header,
    format_forward_text_block,
    format_user_text_block,
    join_prompt_blocks,
)


def _forward_text_message(*, username: str | None = "alice") -> Message:
    sender = User(id=1, is_bot=False, first_name="Alice", username=username)
    origin = MessageOriginUser(
        date=datetime(2026, 5, 29, tzinfo=timezone.utc),
        sender_user=sender,
    )
    message = MagicMock(spec=Message)
    message.forward_origin = origin
    message.text = "hello"
    return message


def test_format_forward_header_with_username():
    header = format_forward_header(_forward_text_message())
    assert "Forwarded" in header
    assert "@alice" in header


def test_format_forward_text_block():
    block = format_forward_text_block(_forward_text_message(), "hello")
    assert "hello" in block
    assert block.startswith("[")


def test_format_user_text_block():
    assert "Your message" in format_user_text_block("fix this")


def test_join_prompt_blocks():
    joined = join_prompt_blocks(["a", "b"])
    assert joined == "a\n\n---\n\nb"
