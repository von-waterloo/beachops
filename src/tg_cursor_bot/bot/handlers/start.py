"""Start and help handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.services.inline_keyboards import welcome_keyboard
from tg_cursor_bot.services.ui_copy import build_welcome_message


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None

    mode = await app.users.get_mode(user.id)
    model_key = await app.users.get_cursor_model_key(
        user.id, default=app.settings.cursor_model
    )
    repo = await app.repos.get_active_repo(user.id)
    repos = await app.repos.list_repos(user.id)
    is_admin = app.settings.is_admin(user.id)
    slot = await app.agent_slots.ensure_default_slot(user.id)

    text = build_welcome_message(
        mode=mode,
        model_key=model_key,
        repo=repo,
        is_admin=is_admin,
        has_repos=bool(repos),
        active_agent_label=slot.label,
    )
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=welcome_keyboard(
                has_repos=bool(repos),
                is_admin=is_admin,
                current=mode,
                current_model_key=model_key,
            ),
        )


help_handler = start_handler
