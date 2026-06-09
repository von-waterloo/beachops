"""New agent session handler."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.domain.models import UserMode
from tg_cursor_bot.services.agent_slots import AgentSlotsFullError
from tg_cursor_bot.services.forward_context import clear_forward_context
from tg_cursor_bot.services.ui_copy import agent_new_from_command, agent_slots_full


async def new_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    await clear_forward_context(context, user.id)
    app.active_runs.pop(user.id, None)

    try:
        slot = await app.agent_slots.create_new_slot(user.id)
    except AgentSlotsFullError:
        await update.message.reply_text(agent_slots_full(app.agent_slots.max_slots))
        return

    await app.users.set_mode(user.id, UserMode.ASK)
    await update.message.reply_text(agent_new_from_command(slot.label))
