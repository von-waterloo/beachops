"""Voice message handler."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from uuid import uuid4

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.run_executor import validate_prompt_request
from beachops.services.inline_keyboards import voice_confirmation_keyboard
from beachops.services.redaction import redact_text
from beachops.services.status_animation import AnimatedStatus, initial_status_text
from beachops.services.telegram_feedback import clear_reaction, mark_received
from beachops.services.forward_context import (
    TriggerPayload,
    get_forward_context_buffer,
)
from beachops.services.prompt_coalesce import get_prompt_coalesce
from beachops.services.ui_copy import voice_error, voice_no_speech

logger = logging.getLogger(__name__)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None or message.voice is None:
        return

    app: AppContext = context.application.bot_data["app"]

    error = await validate_prompt_request(app, user.id)
    if error:
        logger.info(
            "Voice rejected by validation",
            extra={"user_id": user.id, "action": "voice_telegram"},
        )
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

    # Flush any pending text/photos first so they are not lost.
    await get_prompt_coalesce(context).flush_now(context, user_id=user.id)

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
            logger.warning(
                "Voice empty transcript",
                extra={"user_id": user.id, "action": "voice_telegram", "error_code": "empty_transcript"},
            )
            await status.edit_text(voice_no_speech())
            return

        app.remember_user_message(user.id, message.message_id or 0)
        draft_id = str(uuid4())
        mode = await app.users.get_mode(user.id)
        logger.info(
            "Voice draft ready",
            extra={
                "user_id": user.id,
                "action": "voice_telegram",
                "correlation_id": draft_id,
            },
        )
        encrypted = app.payload_crypto.encrypt_json(
            {"text": text, "mode": mode.value}
        )
        await app.redis.set(
            f"beachops:voice-draft:{user.id}:{draft_id}",
            encrypted,
            ex=600,
        )
        preview = redact_text(text)
        if len(preview) > 1200:
            preview = f"{preview[:1200]}…"
        await status.edit_text(
            f"Проверьте расшифровку перед отправкой:\n\n{preview}",
            reply_markup=voice_confirmation_keyboard(draft_id),
        )
    except Exception:
        logger.exception(
            "Voice handling failed",
            extra={"user_id": user.id, "action": "voice_telegram"},
        )
        try:
            await status.edit_text(voice_error())
        except BadRequest:
            await message.reply_text(voice_error())
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        await clear_reaction(message)
