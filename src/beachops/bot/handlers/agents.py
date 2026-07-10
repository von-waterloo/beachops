"""Named Cursor agent slot management."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.bot.handlers.agent_list_ui import send_agent_list
from beachops.services.inline_keyboards import agent_delete_confirm_keyboard
from beachops.services.ui_copy import (
    agent_delete_confirm,
    agent_delete_failed,
    agent_delete_last,
    agent_rename_failed,
    agent_rename_usage,
    agent_renamed,
)


async def agents_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    args = context.args or []
    if len(args) >= 1 and args[0] == "rename":
        name = " ".join(args[1:]).strip()
        if not name:
            await update.message.reply_text(agent_rename_usage())
            return
        slot = await app.agent_slots.rename_active(user.id, name)
        if slot is None:
            await update.message.reply_text(agent_rename_failed())
            return
        await update.message.reply_text(agent_renamed(slot.label))
        return

    if len(args) >= 1 and args[0] == "delete":
        active = await app.agent_slots.get_active(user.id)
        if active is None:
            await update.message.reply_text(agent_delete_failed())
            return
        slots = await app.agent_slots.list_slots(user.id)
        if len(slots) <= 1:
            await update.message.reply_text(agent_delete_last())
            return
        # Same confirm dialog as the inline "🗑 Удалить" button — avoids
        # accidental data loss from a single mistyped command.
        await update.message.reply_text(
            agent_delete_confirm(active.label),
            reply_markup=agent_delete_confirm_keyboard(active.id),
        )
        return

    await send_agent_list(
        bot=update.message.get_bot(),
        chat_id=update.message.chat_id,
        app=app,
        user_id=user.id,
    )
