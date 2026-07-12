"""Telegram stream renderer: cancel keyboard must not stick after finalize."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from beachops.domain.cursor_models import CursorModelKey
from beachops.domain.models import UserMode
from beachops.services.inline_keyboards import CB_CANCEL, post_run_keyboard
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
    msg.get_bot.return_value = bot
    return msg


def _renderer(message: MagicMock) -> TelegramStreamRenderer:
    return TelegramStreamRenderer(
        message,
        header="repo · ask",
        is_admin=True,
        mode=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        min_edit_interval=60.0,
    )


@pytest.mark.asyncio
async def test_finalize_replaces_cancel_with_post_run_keyboard() -> None:
    message = _message()
    renderer = _renderer(message)
    state = StreamState(assistant_text="готово", status="finished")
    markup = post_run_keyboard(
        is_admin=True,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
    )

    await renderer.finalize(state, footer="✅ Готово", reply_markup=markup)

    assert message.edit_text.await_count >= 1
    kwargs = message.edit_text.await_args.kwargs
    applied = kwargs["reply_markup"]
    callbacks = {
        b.callback_data for row in applied.inline_keyboard for b in row
    }
    assert CB_CANCEL not in callbacks
    await renderer.shutdown()


@pytest.mark.asyncio
async def test_finalize_updates_markup_when_text_unchanged() -> None:
    message = _message()
    message.edit_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )
    renderer = _renderer(message)
    state = StreamState(assistant_text="то же", status="finished")
    markup = post_run_keyboard(
        is_admin=True,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
    )

    await renderer.finalize(state, footer="", reply_markup=markup)

    message.edit_reply_markup.assert_awaited()
    applied = message.edit_reply_markup.await_args.kwargs["reply_markup"]
    callbacks = {
        b.callback_data for row in applied.inline_keyboard for b in row
    }
    assert CB_CANCEL not in callbacks
    await renderer.shutdown()


@pytest.mark.asyncio
async def test_flush_does_not_send_message_draft() -> None:
    """Draft streaming must not run alongside edit_text — it duplicates status in chat."""
    message = _message()
    bot = message.get_bot()
    bot.send_message_draft = AsyncMock()
    renderer = _renderer(message)
    renderer._min_edit_interval = 0.0
    state = StreamState(assistant_text="думаю", status="running", agent_id="bc-1")

    await renderer.update(state)
    await renderer.shutdown()

    message.edit_text.assert_awaited()
    bot.send_message_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_closed_pulse_does_not_reapply_cancel() -> None:
    message = _message()
    renderer = _renderer(message)
    renderer._pending = StreamState(assistant_text="x", status="running")
    renderer._closed = True

    await renderer._flush(from_pulse=True)

    message.edit_text.assert_not_awaited()
    await renderer.shutdown()
