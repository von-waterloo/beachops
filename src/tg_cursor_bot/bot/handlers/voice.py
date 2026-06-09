"""Voice message handler."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.services.inline_keyboards import retry_keyboard
from tg_cursor_bot.services.run_executor import submit_user_prompt, validate_prompt_request
from tg_cursor_bot.services.status_animation import AnimatedStatus, initial_status_text
from tg_cursor_bot.services.telegram_feedback import clear_reaction, mark_received
from tg_cursor_bot.services.forward_context import (
    TriggerPayload,
    get_forward_context_buffer,
)
from tg_cursor_bot.services.ui_copy import voice_error, voice_no_speech

logger = logging.getLogger(__name__)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None or message.voice is None:
        return

    app: AppContext = context.application.bot_data["app"]

    error = await validate_prompt_request(app, user.id)
    if error:
        await message.reply_text(error)
        return

    buffer = get_forward_context_buffer(context)
    if buffer.has_items(user.id):
        await mark_received(message)
        try:
            await buffer.flush_with_trigger(
                context,
                user_id=user.id,
                trigger=TriggerPayload(voice_message=message),
            )
        finally:
            await clear_reaction(message)
        return

    await mark_received(message)
    status = await message.reply_text(initial_status_text(preset="downloading"))

    tmp_path: Path | None = None
    try:
        async with AnimatedStatus(status, preset="downloading"):
            tg_file = await message.voice.get_file()
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            await tg_file.download_to_drive(custom_path=str(tmp_path))

        async with AnimatedStatus(status, preset="recognition"):
            text = await app.transcription.transcribe_file(tmp_path)

        if not text:
            await status.edit_text(voice_no_speech())
            return

        try:
            await status.delete()
        except BadRequest:
            pass

        await submit_user_prompt(context=context, user_id=user.id, prompt=text)
    except Exception:
        logger.exception("Voice handling failed")
        try:
            await status.edit_text(voice_error(), reply_markup=retry_keyboard())
        except BadRequest:
            await message.reply_text(voice_error(), reply_markup=retry_keyboard())
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        await clear_reaction(message)
