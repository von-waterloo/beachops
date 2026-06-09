"""PDF and DOCX document message handler."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.services.inline_keyboards import retry_keyboard
from tg_cursor_bot.services.run_executor import submit_user_prompt, validate_prompt_request
from tg_cursor_bot.services.status_animation import AnimatedStatus, initial_status_text
from tg_cursor_bot.services.telegram_documents import (
    DocumentEmptyError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
    build_document_prompt,
    extract_message_document_text,
    is_supported_document_message,
)
from tg_cursor_bot.services.telegram_feedback import clear_reaction, mark_received
from tg_cursor_bot.services.ui_copy import (
    document_empty,
    document_error,
    document_too_large,
    document_truncated,
)

logger = logging.getLogger(__name__)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None or not is_supported_document_message(message):
        return

    app: AppContext = context.application.bot_data["app"]

    error = await validate_prompt_request(app, user.id)
    if error:
        await message.reply_text(error)
        return

    await mark_received(message)
    status = await message.reply_text(initial_status_text(preset="downloading_document"))

    try:
        settings = app.settings
        async with AnimatedStatus(status, preset="downloading_document"):
            filename, text, was_truncated = await extract_message_document_text(
                message,
                max_bytes=settings.document_max_bytes,
                max_chars=settings.document_max_chars,
            )

        prompt = build_document_prompt(
            caption=message.caption,
            filename=filename,
            text=text,
        )

        try:
            await status.delete()
        except BadRequest:
            pass

        if was_truncated:
            await context.bot.send_message(
                chat_id=user.id,
                text=document_truncated(settings.document_max_chars),
            )

        await submit_user_prompt(
            context=context,
            user_id=user.id,
            prompt=prompt,
        )
    except DocumentTooLargeError as exc:
        size = int(exc.args[0]) if exc.args else None
        await status.edit_text(document_too_large(size, app.settings.document_max_bytes))
    except DocumentEmptyError:
        await status.edit_text(document_empty())
    except UnsupportedDocumentError:
        await status.edit_text(document_error())
    except Exception:
        logger.exception("Document handling failed")
        try:
            await status.edit_text(document_error(), reply_markup=retry_keyboard())
        except BadRequest:
            await message.reply_text(document_error(), reply_markup=retry_keyboard())
    finally:
        await clear_reaction(message)
