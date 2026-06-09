"""Cancel active run and clear queue."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tg_cursor_bot.bot.handlers.agent_rename import cancel_pending_rename
from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.services.cancel_service import cancel_user_work
from tg_cursor_bot.services.forward_context import clear_forward_context, get_forward_context_buffer
from tg_cursor_bot.services.ui_copy import cancel_failed, cancel_none, cancel_ok


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    if await cancel_pending_rename(update, context):
        return

    buffer = get_forward_context_buffer(context)
    forward_count = buffer.item_count(user.id)

    session = await app.agent_slots.get_active(user.id)
    pending = app.job_queue.pending_count(user.id)
    if (
        not (session and session.active_run_id)
        and not app.job_queue.is_active(user.id)
        and pending == 0
        and forward_count == 0
    ):
        await update.message.reply_text(cancel_none())
        return

    cleared_forward = await clear_forward_context(context, user.id)
    outcome = await cancel_user_work(app, user.id)
    if outcome.cancelled_run or outcome.cleared_queue or cleared_forward:
        await update.message.reply_text(
            cancel_ok(cleared_queue=outcome.cleared_queue, cleared_forwards=cleared_forward)
        )
    else:
        await update.message.reply_text(cancel_failed())
