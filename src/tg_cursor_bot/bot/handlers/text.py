"""Plain text message handler."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tg_cursor_bot.bot.handlers.agent_rename import try_consume_rename_text
from tg_cursor_bot.services.run_executor import submit_user_prompt
from tg_cursor_bot.services.telegram_feedback import clear_reaction, mark_received
from tg_cursor_bot.services.forward_context import (
    TriggerPayload,
    get_forward_context_buffer,
)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or not message.text:
        return

    text = message.text.strip()
    if not text or text.startswith("/"):
        return

    user = update.effective_user
    assert user is not None

    if await try_consume_rename_text(update, context):
        return

    buffer = get_forward_context_buffer(context)
    if buffer.has_items(user.id):
        await mark_received(message)
        try:
            await buffer.flush_with_trigger(
                context,
                user_id=user.id,
                trigger=TriggerPayload(text=text),
            )
        finally:
            await clear_reaction(message)
        return

    await mark_received(message)
    try:
        await submit_user_prompt(
            context=context,
            user_id=user.id,
            prompt=text,
        )
    finally:
        await clear_reaction(message)
