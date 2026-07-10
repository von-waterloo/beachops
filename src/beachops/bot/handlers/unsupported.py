"""Fallback for message types the bot does not process."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.services.ui_copy import unsupported_media_message


def _is_unsupported_message(message) -> bool:
    if message.sticker or message.video or message.animation:
        return True
    if message.audio or message.video_note:
        return True
    if message.document:
        mime = (message.document.mime_type or "").lower()
        if mime in {"application/pdf"}:
            return False
        if mime.startswith("image/"):
            return False
        name = (message.document.file_name or "").lower()
        if name.endswith(".docx"):
            return False
        return True
    return False


async def unsupported_media_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.message
    if message is None or not _is_unsupported_message(message):
        return
    await message.reply_text(unsupported_media_message())
