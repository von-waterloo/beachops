"""Debounce text + photos from one user into a single Cursor prompt.

Telegram often delivers a caption/text update before attached images finish
uploading, so an immediate text handler would start a run without pictures.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from cursor_sdk import SDKImage
from telegram import Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.run_executor import submit_user_prompt, validate_prompt_request
from beachops.services.status_animation import AnimatedStatus, initial_status_text
from beachops.services.telegram_feedback import clear_reaction, mark_received
from beachops.services.telegram_images import (
    TelegramDownloadError,
    UnsupportedImageError,
    build_prompt_text,
    download_message_as_sdk_image,
    extract_group_caption,
    message_has_image,
)
from beachops.services.ui_copy import (
    photo_download_timeout,
    photo_error,
    photo_partial_download,
    photo_too_many,
    photo_unsupported_document,
)

logger = logging.getLogger(__name__)

_COALESCE_KEY = "prompt_coalesce"


@dataclass
class _PendingPrompt:
    texts: list[str] = field(default_factory=list)
    photo_messages: list[Message] = field(default_factory=list)
    reaction_messages: list[Message] = field(default_factory=list)
    flush_task: asyncio.Task[None] | None = None


class PromptCoalesceBuffer:
    """Per-user quiet-period buffer for text and image messages."""

    def __init__(
        self,
        *,
        delay_sec: float,
        max_images: int,
    ) -> None:
        self._delay_sec = max(0.0, delay_sec)
        self._max_images = max_images
        self._pending: dict[int, _PendingPrompt] = {}
        self._lock = asyncio.Lock()

    @property
    def delay_sec(self) -> float:
        return self._delay_sec

    def has_pending(self, user_id: int) -> bool:
        pending = self._pending.get(user_id)
        return pending is not None and (
            bool(pending.texts) or bool(pending.photo_messages)
        )

    async def add_text(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        text: str,
        message: Message,
    ) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        app: AppContext = context.application.bot_data["app"]
        app.remember_user_message(user_id, message.message_id or 0)
        await mark_received(message)
        async with self._lock:
            pending = self._ensure_locked(user_id)
            pending.texts.append(cleaned)
            self._track_reaction_locked(pending, message)
            self._reschedule_locked(context, user_id, pending)

    async def add_photo(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        message: Message,
    ) -> None:
        if not message_has_image(message):
            return
        app: AppContext = context.application.bot_data["app"]
        app.remember_user_message(user_id, message.message_id or 0)
        await mark_received(message)
        async with self._lock:
            pending = self._ensure_locked(user_id)
            if message.message_id not in {m.message_id for m in pending.photo_messages}:
                pending.photo_messages.append(message)
            self._track_reaction_locked(pending, message)
            self._reschedule_locked(context, user_id, pending)

    async def clear(self, user_id: int) -> bool:
        """Drop pending coalesce for user. Returns True if something was cleared."""
        async with self._lock:
            pending = self._pending.pop(user_id, None)
            if pending is None:
                return False
            if pending.flush_task is not None:
                pending.flush_task.cancel()
            had_content = bool(pending.texts or pending.photo_messages)
            messages = list(pending.reaction_messages)
        for msg in messages:
            await clear_reaction(msg)
        return had_content

    async def flush_now(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
    ) -> None:
        """Flush immediately (e.g. before an unrelated voice prompt)."""
        async with self._lock:
            pending = self._pending.get(user_id)
            if pending is None:
                return
            if pending.flush_task is not None:
                pending.flush_task.cancel()
                pending.flush_task = None
        await self._flush_user(context, user_id)

    def _ensure_locked(self, user_id: int) -> _PendingPrompt:
        pending = self._pending.get(user_id)
        if pending is None:
            pending = _PendingPrompt()
            self._pending[user_id] = pending
        return pending

    def _track_reaction_locked(self, pending: _PendingPrompt, message: Message) -> None:
        if message.message_id not in {m.message_id for m in pending.reaction_messages}:
            pending.reaction_messages.append(message)

    def _reschedule_locked(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        pending: _PendingPrompt,
    ) -> None:
        if pending.flush_task is not None:
            pending.flush_task.cancel()
        pending.flush_task = asyncio.create_task(
            self._delayed_flush(context, user_id),
            name=f"prompt_coalesce_{user_id}",
        )

    async def _delayed_flush(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
    ) -> None:
        try:
            if self._delay_sec > 0:
                await asyncio.sleep(self._delay_sec)
            await self._flush_user(context, user_id)
        except asyncio.CancelledError:
            raise

    async def _flush_user(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
    ) -> None:
        async with self._lock:
            pending = self._pending.pop(user_id, None)
            if pending is None:
                return
            pending.flush_task = None
            texts = list(pending.texts)
            photo_messages = sorted(
                pending.photo_messages,
                key=lambda m: m.message_id or 0,
            )
            reaction_messages = list(pending.reaction_messages)

        if not texts and not photo_messages:
            return

        try:
            await self._submit_pending(
                context,
                user_id=user_id,
                texts=texts,
                photo_messages=photo_messages,
            )
        finally:
            for msg in reaction_messages:
                await clear_reaction(msg)

    async def _submit_pending(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        texts: list[str],
        photo_messages: list[Message],
    ) -> None:
        app: AppContext = context.application.bot_data["app"]
        error = await validate_prompt_request(app, user_id)
        if error:
            await context.bot.send_message(chat_id=user_id, text=error)
            return

        prompt = _compose_prompt(texts, photo_messages)
        images: list[SDKImage] = []
        status_msg: Message | None = None
        anchor = photo_messages[0] if photo_messages else None
        failed_downloads = 0

        try:
            if photo_messages:
                if anchor is not None:
                    status_msg = await anchor.reply_text(
                        initial_status_text(preset="downloading_images")
                    )
                    async with AnimatedStatus(status_msg, preset="downloading_images"):
                        for msg in photo_messages:
                            try:
                                images.append(await download_message_as_sdk_image(msg))
                            except UnsupportedImageError:
                                logger.debug(
                                    "Skipping unsupported image in coalesce",
                                    exc_info=True,
                                )
                            except TelegramDownloadError:
                                logger.warning(
                                    "Telegram image download failed in coalesce",
                                    exc_info=True,
                                )
                                failed_downloads += 1
                    try:
                        await status_msg.delete()
                    except BadRequest:
                        pass
                    status_msg = None
                else:
                    for msg in photo_messages:
                        try:
                            images.append(await download_message_as_sdk_image(msg))
                        except UnsupportedImageError:
                            logger.debug(
                                "Skipping unsupported image in coalesce",
                                exc_info=True,
                            )
                        except TelegramDownloadError:
                            logger.warning(
                                "Telegram image download failed in coalesce",
                                exc_info=True,
                            )
                            failed_downloads += 1

                if not images and not texts:
                    reply = (
                        photo_download_timeout()
                        if failed_downloads
                        else photo_unsupported_document()
                    )
                    if anchor is not None:
                        await anchor.reply_text(reply)
                    else:
                        await context.bot.send_message(chat_id=user_id, text=reply)
                    return

            if len(images) > self._max_images:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=photo_too_many(len(images), self._max_images),
                )
                return

            if failed_downloads and images:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=photo_partial_download(failed_downloads, len(photo_messages)),
                )

            await submit_user_prompt(
                context=context,
                user_id=user_id,
                prompt=prompt,
                images=images or None,
            )
        except TelegramDownloadError:
            logger.exception("Prompt coalesce flush failed for user %s", user_id)
            reply = photo_download_timeout()
            if status_msg is not None:
                try:
                    await status_msg.edit_text(reply)
                    return
                except BadRequest:
                    pass
            await context.bot.send_message(chat_id=user_id, text=reply)
        except Exception:
            logger.exception("Prompt coalesce flush failed for user %s", user_id)
            if status_msg is not None:
                try:
                    await status_msg.edit_text(photo_error())
                    return
                except BadRequest:
                    pass
            await context.bot.send_message(chat_id=user_id, text=photo_error())


def _compose_prompt(texts: list[str], photo_messages: list[Message]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for text in texts:
        cleaned = text.strip()
        if cleaned and cleaned not in seen:
            parts.append(cleaned)
            seen.add(cleaned)
    caption = extract_group_caption(photo_messages)
    if caption:
        cleaned = caption.strip()
        if cleaned and cleaned not in seen:
            parts.append(cleaned)
    if parts:
        return "\n\n".join(parts)
    return build_prompt_text(None)


def get_prompt_coalesce(context: ContextTypes.DEFAULT_TYPE) -> PromptCoalesceBuffer:
    buf = context.application.bot_data.get(_COALESCE_KEY)
    if buf is None:
        raise RuntimeError("PromptCoalesceBuffer not initialized")
    return buf


def init_prompt_coalesce(application) -> None:
    app: AppContext = application.bot_data["app"]
    settings = app.settings
    application.bot_data[_COALESCE_KEY] = PromptCoalesceBuffer(
        delay_sec=settings.prompt_coalesce_sec,
        max_images=settings.photo_max_count,
    )


async def clear_prompt_coalesce(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    return await get_prompt_coalesce(context).clear(user_id)
