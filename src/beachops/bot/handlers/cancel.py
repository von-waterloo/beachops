"""Cancel active run and clear queue."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.bot.handlers.agent_rename import cancel_pending_rename
from beachops.app_context import AppContext
from beachops.services.cancel_service import cancel_user_work, cancel_was_successful
from beachops.services.forward_context import clear_forward_context, get_forward_context_buffer
from beachops.services.prompt_coalesce import clear_prompt_coalesce, get_prompt_coalesce
from beachops.services.telegram_images import get_media_group_collector
from beachops.services.ui_copy import cancel_failed, cancel_none, cancel_ok


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    if await cancel_pending_rename(update, context):
        return

    buffer = get_forward_context_buffer(context)
    forward_count = buffer.item_count(user.id)
    coalesce_pending = get_prompt_coalesce(context).has_pending(user.id)
    try:
        media_groups = get_media_group_collector(context)
        album_pending = media_groups.has_pending_for_user(user.id)
    except RuntimeError:
        media_groups = None
        album_pending = False

    session = await app.agent_slots.get_active(user.id)
    pending = app.job_queue.pending_count(user.id)
    if (
        not (session and session.active_run_id)
        and not app.job_queue.is_active(user.id)
        and pending == 0
        and forward_count == 0
        and not coalesce_pending
        and not album_pending
    ):
        await update.message.reply_text(cancel_none())
        return

    cleared_forward = await clear_forward_context(context, user.id)
    cleared_coalesce = await clear_prompt_coalesce(context, user.id)
    cleared_albums = 0
    if media_groups is not None:
        cleared_albums = await media_groups.clear_for_user(user.id)
    outcome = await cancel_user_work(app, user.id, bot=context.bot)
    if cancel_was_successful(
        outcome,
        cleared_forward=bool(cleared_forward),
        cleared_coalesce=bool(cleared_coalesce) or cleared_albums > 0,
    ):
        await update.message.reply_text(
            cancel_ok(
                cleared_queue=outcome.cleared_queue,
                cleared_forwards=cleared_forward,
                cleared_coalesce=bool(cleared_coalesce),
            )
        )
    else:
        await update.message.reply_text(cancel_failed())
