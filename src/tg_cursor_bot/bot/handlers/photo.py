"""Photo and image-document message handler."""

from __future__ import annotations

import logging

from cursor_sdk import SDKImage
from telegram import Message, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.services.inline_keyboards import retry_keyboard
from tg_cursor_bot.services.run_executor import submit_user_prompt, validate_prompt_request
from tg_cursor_bot.services.status_animation import AnimatedStatus, initial_status_text
from tg_cursor_bot.services.telegram_feedback import clear_reaction, mark_received
from tg_cursor_bot.services.telegram_images import (
    UnsupportedImageError,
    build_prompt_text,
    download_message_as_sdk_image,
    extract_group_caption,
    get_media_group_collector,
    init_media_group_collector,
    limit_sdk_images,
    message_has_image,
    is_supported_image_mime,
)
from tg_cursor_bot.services.ui_copy import (
    photo_error,
    photo_too_many,
    photo_unsupported_document,
)

logger = logging.getLogger(__name__)


def register_media_group_collector(application) -> None:
    init_media_group_collector(
        application,
        on_flush=_make_flush_callback(application),
    )


def _make_flush_callback(application):
    async def on_flush(user_id: int, messages: list[Message]) -> None:
        await _process_photo_messages(
            application,
            user_id=user_id,
            messages=messages,
        )

    return on_flush


def _bot_data_app(context) -> AppContext:
    if hasattr(context, "application"):
        return context.application.bot_data["app"]
    return context.bot_data["app"]


def _bot(context):
    if hasattr(context, "application"):
        return context.bot
    return context.bot


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

    error = await validate_prompt_request(app, user.id)
    if error:
        await message.reply_text(error)
        return

    if message.media_group_id:
        collector = get_media_group_collector(context)
        buffered = await collector.add(context, user_id=user.id, message=message)
        if buffered:
            await mark_received(message)
        return

    await _process_single_photo(context, user_id=user.id, message=message)


async def _process_single_photo(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    message: Message,
) -> None:
    await mark_received(message)
    status = await message.reply_text(initial_status_text(preset="downloading_images"))

    try:
        async with AnimatedStatus(status, preset="downloading_images"):
            sdk_image = await download_message_as_sdk_image(message)
            prompt = build_prompt_text(message.caption)

        try:
            await status.delete()
        except BadRequest:
            pass

        app = _bot_data_app(context)
        images, dropped = limit_sdk_images(
            [sdk_image],
            max_count=app.settings.photo_max_count,
        )
        if dropped:
            await _bot(context).send_message(
                chat_id=user_id,
                text=photo_too_many(1 + dropped, len(images)),
            )

        await submit_user_prompt(
            context=context,
            user_id=user_id,
            prompt=prompt,
            images=images,
        )
    except UnsupportedImageError:
        await status.edit_text(photo_unsupported_document())
    except Exception:
        logger.exception("Photo handling failed")
        try:
            await status.edit_text(photo_error(), reply_markup=retry_keyboard())
        except BadRequest:
            await message.reply_text(photo_error(), reply_markup=retry_keyboard())
    finally:
        await clear_reaction(message)


async def _process_photo_messages(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    messages: list[Message],
) -> None:
    if not messages:
        return

    first = messages[0]
    status = await first.reply_text(initial_status_text(preset="downloading_images"))

    try:
        sdk_images: list[SDKImage] = []
        async with AnimatedStatus(status, preset="downloading_images"):
            for msg in messages:
                if not message_has_image(msg):
                    continue
                try:
                    sdk_images.append(await download_message_as_sdk_image(msg))
                except UnsupportedImageError:
                    logger.debug("Skipping unsupported image in album", exc_info=True)

        if not sdk_images:
            await status.edit_text(photo_unsupported_document())
            return

        app = _bot_data_app(context)
        original_count = len(sdk_images)
        images, dropped = limit_sdk_images(
            sdk_images,
            max_count=app.settings.photo_max_count,
        )
        prompt = build_prompt_text(extract_group_caption(messages))

        try:
            await status.delete()
        except BadRequest:
            pass

        if dropped:
            await _bot(context).send_message(
                chat_id=user_id,
                text=photo_too_many(original_count, app.settings.photo_max_count),
            )

        await submit_user_prompt(
            context=context,
            user_id=user_id,
            prompt=prompt,
            images=images,
        )
    except Exception:
        logger.exception("Photo album handling failed")
        try:
            await status.edit_text(photo_error(), reply_markup=retry_keyboard())
        except BadRequest:
            await first.reply_text(photo_error(), reply_markup=retry_keyboard())
    finally:
        for msg in messages:
            await clear_reaction(msg)
