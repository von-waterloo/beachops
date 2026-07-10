"""BeachOps durable jobs and approvals screens."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.domain.security import Role
from beachops.services.ui_copy import approvals_message, jobs_message


async def jobs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        return
    role = app.settings.role_for(user.id)
    jobs = (
        await app.jobs.list_all_internal(limit=10)
        if role == Role.OWNER
        else await app.jobs.list_for_actor(user.id, limit=10)
    )
    await message.reply_text(jobs_message(jobs))


async def approvals_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        return
    if app.settings.role_for(user.id) != Role.OWNER:
        await message.reply_text("Подтверждения доступны только владельцу.")
        return
    approvals = await app.approvals.list_pending(limit=10)
    await message.reply_text(approvals_message(approvals))
