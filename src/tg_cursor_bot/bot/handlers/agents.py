"""Named Cursor agent slot management."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.bot.handlers.agent_list_ui import send_agent_list
from tg_cursor_bot.services.agent_rename_pending import clear_pending, peek_pending
from tg_cursor_bot.services.agent_slots import AgentSlotLastError
from tg_cursor_bot.services.cancel_service import cancel_user_work
from tg_cursor_bot.services.ui_copy import (
    agent_delete_failed,
    agent_delete_last,
    agent_deleted,
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
        if (
            active.active_run_id
            or app.job_queue.is_active(user.id)
            or app.job_queue.pending_count(user.id) > 0
        ):
            await cancel_user_work(app, user.id)
        if peek_pending(context) == active.id:
            clear_pending(context)
        try:
            new_active = await app.agent_slots.delete_slot(user.id, active.id)
        except AgentSlotLastError:
            await update.message.reply_text(agent_delete_last())
            return
        if new_active is None:
            await update.message.reply_text(agent_delete_failed())
            return
        await update.message.reply_text(
            agent_deleted(active.label, new_active_label=new_active.label),
        )
        await send_agent_list(
            bot=update.message.get_bot(),
            chat_id=update.message.chat_id,
            app=app,
            user_id=user.id,
        )
        return

    await send_agent_list(
        bot=update.message.get_bot(),
        chat_id=update.message.chat_id,
        app=app,
        user_id=user.id,
    )
