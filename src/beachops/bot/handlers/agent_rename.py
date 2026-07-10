"""Inline and text-flow agent rename."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.bot.handlers.agent_list_ui import send_agent_list
from beachops.services.agent_rename_pending import clear_pending, peek_pending, set_pending
from beachops.services.ui_copy import (
    agent_rename_failed,
    agent_rename_prompt,
    agent_renamed,
    agent_rename_cancelled,
)


async def start_agent_rename(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    bot,
    slot_id: int,
    current_label: str,
) -> None:
    set_pending(context, slot_id)
    await bot.send_message(chat_id=chat_id, text=agent_rename_prompt(current_label))


async def try_consume_rename_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    slot_id = peek_pending(context)
    if slot_id is None:
        return False

    message = update.message
    user = update.effective_user
    if message is None or user is None or not message.text:
        return False

    name = message.text.strip()
    if not name:
        return False

    app: AppContext = context.application.bot_data["app"]
    clear_pending(context)
    slot = await app.agent_slots.rename_slot(user.id, slot_id, name)
    if slot is None:
        await message.reply_text(agent_rename_failed())
        return True

    await message.reply_text(agent_renamed(slot.label))
    await send_agent_list(
        bot=message.get_bot(),
        chat_id=message.chat_id,
        app=app,
        user_id=user.id,
    )
    return True


async def cancel_pending_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if peek_pending(context) is None:
        return False
    clear_pending(context)
    assert update.message is not None
    await update.message.reply_text(agent_rename_cancelled())
    return True
