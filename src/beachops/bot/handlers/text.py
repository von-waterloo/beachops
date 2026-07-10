"""Plain text message handler."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.bot.handlers.agent_rename import try_consume_rename_text
from beachops.services.telegram_feedback import clear_reaction, mark_received
from beachops.services.forward_context import (
    TriggerPayload,
    get_forward_context_buffer,
)
from beachops.services.prompt_coalesce import get_prompt_coalesce


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
                trigger=TriggerPayload(text=text, message_id=message.message_id),
            )
        finally:
            await clear_reaction(message)
        return

    await get_prompt_coalesce(context).add_text(
        context,
        user_id=user.id,
        text=text,
        message=message,
    )
