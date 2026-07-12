"""Bot status snapshot."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.cursor_token_ui import token_ui_pair
from beachops.services.forward_context import get_forward_context_buffer
from beachops.services.inline_keyboards import status_reply_markup
from beachops.services.ui_copy import build_status_message


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
    token_key, available_tokens = await token_ui_pair(app, user.id)

    pending = await app.jobs.count_pending_for_actor(user.id)
    active_job = await app.jobs.latest_active_for_actor(user.id)
    is_active = app.job_queue.is_active(user.id) or active_job is not None
    pending_count = max(
        app.job_queue.pending_count(user.id),
        max(0, pending - (1 if active_job else 0)),
    )

    text = build_status_message(
        mode=mode,
        model_key=model_key,
        repo=repo,
        is_active=is_active,
        pending_count=pending_count,
        has_active_run=bool(slot.active_run_id) or active_job is not None,
        forward_buffer_count=forward_count,
        active_agent_label=slot.label,
        token_key=token_key,
    )
    await update.message.reply_text(
        text,
        reply_markup=status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
            current_token_key=token_key,
            available_token_keys=available_tokens,
        ),
    )
