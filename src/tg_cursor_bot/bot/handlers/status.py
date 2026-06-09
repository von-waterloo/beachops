"""Bot status snapshot."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.services.forward_context import get_forward_context_buffer
from tg_cursor_bot.services.inline_keyboards import status_reply_markup
from tg_cursor_bot.services.ui_copy import build_status_message


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    mode = await app.users.get_mode(user.id)
    model_key = await app.users.get_cursor_model_key(
        user.id, default=app.settings.cursor_model
    )
    repo = await app.repos.get_active_repo(user.id)
    slot = await app.agent_slots.ensure_default_slot(user.id)
    is_admin = app.settings.is_admin(user.id)
    forward_count = get_forward_context_buffer(context).item_count(user.id)
    repos = await app.repos.list_repos(user.id)

    text = build_status_message(
        mode=mode,
        model_key=model_key,
        repo=repo,
        is_active=app.job_queue.is_active(user.id),
        pending_count=app.job_queue.pending_count(user.id),
        has_active_run=bool(slot.active_run_id),
        forward_buffer_count=forward_count,
        active_agent_label=slot.label,
    )
    await update.message.reply_text(
        text,
        reply_markup=status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
        ),
    )
