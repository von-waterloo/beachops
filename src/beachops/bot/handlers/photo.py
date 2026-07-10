"""Photo and image-document message handler."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.prompt_coalesce import get_prompt_coalesce
from beachops.services.run_executor import validate_prompt_request
from beachops.services.telegram_images import (
    get_media_group_collector,
    is_supported_image_mime,
    message_has_image,
)
from beachops.services.ui_copy import photo_unsupported_document


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    if message.document and not message.photo:
        mime = message.document.mime_type
        if not is_supported_image_mime(mime):
            await message.reply_text(photo_unsupported_document())
            return

    if not message_has_image(message):
        return

    app: AppContext = context.application.bot_data["app"]
    if message.media_group_id:
        buffered = await get_media_group_collector(context).add(
            context,
            user_id=user.id,
            message=message,
        )
        if buffered:
            return

    error = await validate_prompt_request(app, user.id)
    if error:
        await message.reply_text(error)
        return

    app.remember_user_message(user.id, message.message_id or 0)
    await get_prompt_coalesce(context).add_photo(
        context,
        user_id=user.id,
        message=message,
    )