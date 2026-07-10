"""Mode command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.bot.handlers.status import status_handler
from beachops.domain.models import UserMode
from beachops.services.ui_copy import access_denied_mode, mode_set


async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: UserMode) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    if not app.settings.can_use_mode(user.id, mode):
        await update.message.reply_text(access_denied_mode(mode))
        return

    await app.users.set_mode(user.id, mode)
    await update.message.reply_text(mode_set(mode))


async def ask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_mode(update, context, UserMode.ASK)


async def plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_mode(update, context, UserMode.PLAN)


async def do_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_mode(update, context, UserMode.DO)


async def mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await status_handler(update, context)
