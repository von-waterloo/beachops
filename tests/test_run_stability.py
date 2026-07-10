"""Tests for Telegram timeout isolation and cancel store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import TimedOut

from beachops.domain.cursor_models import CursorModelKey
from beachops.domain.models import UserMode
from beachops.services.cancel_store import CancelStore
from beachops.services.stream_bridge import StreamState
from beachops.services.telegram_renderer import TelegramStreamRenderer


def _message() -> MagicMock:
    msg = MagicMock()
    msg.chat_id = 1
    msg.message_id = 42
    msg.edit_text = AsyncMock()
    msg.edit_reply_markup = AsyncMock()
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    bot.send_message_draft = None
    msg.get_bot.return_value = bot
    return msg


@pytest.mark.asyncio
async def test_update_swallows_telegram_timeout() -> None:
    message = _message()
    message.edit_text = AsyncMock(side_effect=TimedOut("timed out"))
    renderer = TelegramStreamRenderer(
        message,
        header="repo · ask",
        is_admin=True,
        mode=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        min_edit_interval=0.0,
    )
    # Must not raise into Cursor run loop.
    await renderer.update(StreamState(assistant_text="partial", status="running"))
    await renderer.shutdown()


@pytest.mark.asyncio
async def test_finalize_retries_after_timeout_without_raising() -> None:
    message = _message()
    message.edit_text = AsyncMock(side_effect=[TimedOut("timed out"), None])
    renderer = TelegramStreamRenderer(
        message,
        header="repo · ask",
        is_admin=True,
        mode=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        min_edit_interval=60.0,
    )
    await renderer.finalize(StreamState(assistant_text="done", status="finished"))
    assert message.edit_text.await_count >= 1
    await renderer.shutdown()


@pytest.mark.asyncio
async def test_cancel_store_roundtrip() -> None:
    redis = MagicMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock(side_effect=[1, 0])
    store = CancelStore(redis, ttl_sec=60)
    await store.request_cancel(7)
    assert await store.is_cancelled(7) is True
    await store.clear_cancel(7)
    assert await store.is_cancelled(7) is False
    redis.set.assert_awaited()
    redis.delete.assert_awaited()
