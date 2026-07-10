"""New agent session handler."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.domain.models import UserMode
from beachops.services.agent_slots import AgentSlotsFullError
from beachops.services.cancel_service import cancel_user_work
from beachops.services.cursor_token_ui import current_token_key_for_ui
from beachops.services.forward_context import clear_forward_context
from beachops.services.inline_keyboards import status_reply_markup
from beachops.services.ui_copy import agent_new_from_command, agent_slots_full


async def new_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    await clear_forward_context(context, user.id)

    if app.job_queue.is_busy(user.id):
        await cancel_user_work(app, user.id)

    app.active_runs.pop(user.id, None)

    try:
        slot = await app.agent_slots.create_new_slot(user.id)
    except AgentSlotsFullError:
        await update.message.reply_text(agent_slots_full(app.agent_slots.max_slots))
        return

    await app.users.set_mode(user.id, UserMode.ASK)
    is_admin = app.settings.is_admin(user.id)
    model_key = await app.users.get_cursor_model_key(
        user.id, default=app.settings.cursor_model
    )
    repos = await app.repos.list_repos(user.id)
    token_key = await current_token_key_for_ui(app, user.id)
    await update.message.reply_text(
        agent_new_from_command(slot.label),
        reply_markup=status_reply_markup(
            is_admin=is_admin,
            current=UserMode.ASK,
            current_model_key=model_key,
            has_repos=bool(repos),
            current_token_key=token_key,
        ),
    )
