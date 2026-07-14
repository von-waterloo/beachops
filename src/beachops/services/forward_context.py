"""Buffer forwarded messages until user trigger or timeout."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cursor_sdk import SDKImage
from telegram import Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.forward_format import (
    format_forward_text_block,
    format_user_text_block,
    join_prompt_blocks,
)
from beachops.services.run_executor import submit_user_prompt, validate_prompt_request
from beachops.services.job_queue import SubmitResult
from beachops.services.telegram_feedback import clear_reaction
from beachops.services.telegram_documents import (
    DocumentEmptyError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
    extract_message_document_text,
    is_supported_document_message,
)
from beachops.services.telegram_images import (
    TelegramDownloadError,
    UnsupportedImageError,
    build_prompt_text,
    download_message_as_sdk_image,
    extract_group_caption,
    message_has_image,
)
from beachops.services.ui_copy import (
    forward_buffer_full,
    forward_context_default_prompt,
    forward_context_hint,
    forward_context_hint_count,
    forward_flush_failed,
    photo_too_many,
    queue_full_keep_buffer,
)

logger = logging.getLogger(__name__)

_BUFFER_KEY = "forward_context_buffer"
ForwardItemKind = Literal["text", "photo", "album", "voice", "document", "unsupported"]


@dataclass
class ForwardItem:
    kind: ForwardItemKind
    messages: list[Message] = field(default_factory=list)


@dataclass
class _UserBuffer:
    user_id: int
    items: list[ForwardItem] = field(default_factory=list)
    source_messages: list[Message] = field(default_factory=list)
    hint_chat_id: int | None = None
    hint_message_id: int | None = None
    flush_task: asyncio.Task[None] | None = None


@dataclass
class _AlbumBuffer:
    user_id: int
    messages: list[Message] = field(default_factory=list)
    flush_task: asyncio.Task[None] | None = None


@dataclass(frozen=True, slots=True)
class TriggerPayload:
    text: str | None = None
    voice_message: Message | None = None
    message_id: int | None = None


class ForwardContextBuffer:
    def __init__(
        self,
        *,
        timeout_sec: float,
        max_items: int,
        photo_max_count: int,
        document_max_chars: int,
        document_max_bytes: int,
    ) -> None:
        self._timeout_sec = timeout_sec
        self._max_items = max_items
        self._photo_max_count = photo_max_count
        self._document_max_chars = document_max_chars
        self._document_max_bytes = document_max_bytes
        self._buffers: dict[int, _UserBuffer] = {}
        self._albums: dict[str, _AlbumBuffer] = {}
        self._album_processed: set[str] = set()
        self._lock = asyncio.Lock()

    def has_items(self, user_id: int) -> bool:
        buf = self._buffers.get(user_id)
        return bool(buf and buf.items)

    def item_count(self, user_id: int) -> int:
        buf = self._buffers.get(user_id)
        return len(buf.items) if buf else 0

    async def clear(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
        async with self._lock:
            count = len(self._buffers.get(user_id, _UserBuffer(user_id=user_id)).items)
            buf = self._buffers.pop(user_id, None)
            if buf and buf.flush_task is not None:
                buf.flush_task.cancel()
            await self._delete_hint(context, buf)
            self._purge_user_albums_locked(user_id)
        return count

    def _purge_user_albums_locked(self, user_id: int) -> None:
        to_remove = [gid for gid, alb in self._albums.items() if alb.user_id == user_id]
        for gid in to_remove:
            alb = self._albums.pop(gid, None)
            if alb and alb.flush_task is not None:
                alb.flush_task.cancel()

    async def add_forward(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        message: Message,
    ) -> None:
        if message.media_group_id and message_has_image(message):
            await self._add_album_part(context, user_id=user_id, message=message)
            return

        kind = self._classify_message(message)
        async with self._lock:
            buf = self._ensure_buffer_locked(user_id)
            if len(buf.items) >= self._max_items:
                await self._update_hint_locked(context, buf)
                return
            buf.items.append(ForwardItem(kind=kind, messages=[message]))
            buf.source_messages.append(message)
            self._schedule_timeout_locked(context, buf)

        await self._update_hint(context, user_id)

    async def _add_album_part(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        message: Message,
    ) -> None:
        group_id = message.media_group_id
        if not group_id:
            return

        async with self._lock:
            if group_id in self._album_processed:
                return

            alb = self._albums.get(group_id)
            if alb is None:
                alb = _AlbumBuffer(user_id=user_id)
                self._albums[group_id] = alb

            if message.message_id not in {m.message_id for m in alb.messages}:
                alb.messages.append(message)

            if alb.flush_task is not None:
                alb.flush_task.cancel()
            alb.flush_task = asyncio.create_task(
                self._delayed_album_flush(context, group_id),
                name=f"forward_album_{group_id}",
            )

    async def _delayed_album_flush(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        group_id: str,
    ) -> None:
        from beachops.config.settings import get_settings

        delay = get_settings().media_group_delay_sec
        try:
            await asyncio.sleep(delay)
            await self._flush_album_group(context, group_id)
        except asyncio.CancelledError:
            raise

    async def _flush_album_group(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        group_id: str,
    ) -> None:
        async with self._lock:
            alb = self._albums.pop(group_id, None)
            if alb is None or group_id in self._album_processed:
                return
            self._album_processed.add(group_id)
            messages = sorted(alb.messages, key=lambda m: m.message_id or 0)
            user_id = alb.user_id

        try:
            if messages:
                await self.add_album(context, user_id=user_id, messages=messages)
        finally:
            async with self._lock:
                self._album_processed.discard(group_id)

    async def add_album(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        messages: list[Message],
    ) -> None:
        if not messages:
            return
        async with self._lock:
            buf = self._ensure_buffer_locked(user_id)
            if len(buf.items) >= self._max_items:
                await self._update_hint_locked(context, buf)
                return
            buf.items.append(ForwardItem(kind="album", messages=list(messages)))
            buf.source_messages.extend(messages)
            self._schedule_timeout_locked(context, buf)

        await self._update_hint(context, user_id)

    async def flush_with_trigger(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        trigger: TriggerPayload,
    ) -> None:
        await self._flush(context, user_id=user_id, trigger=trigger)

    async def _timeout_flush(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
    ) -> None:
        await self._flush(context, user_id=user_id, trigger=None)

    async def _flush(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        trigger: TriggerPayload | None,
    ) -> None:
        async with self._lock:
            buf = self._buffers.pop(user_id, None)
            if buf is None or not buf.items:
                return
            current = asyncio.current_task()
            if buf.flush_task is not None and buf.flush_task is not current:
                buf.flush_task.cancel()
            items = list(buf.items)
            sources = list(buf.source_messages)
            hint_chat = buf.hint_chat_id
            hint_msg = buf.hint_message_id

        try:
            await self._delete_hint_by_id(context, hint_chat, hint_msg)
            await self._build_and_submit(
                context,
                user_id=user_id,
                items=items,
                sources=sources,
                trigger=trigger,
            )
        except Exception:
            logger.exception("Forward context flush failed for user %s", user_id)
            async with self._lock:
                existing = self._buffers.get(user_id)
                if existing is None:
                    self._buffers[user_id] = _UserBuffer(
                        user_id=user_id,
                        items=items,
                        source_messages=sources,
                    )
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=forward_flush_failed(),
                )
            except BadRequest:
                logger.debug("Could not notify user about forward flush failure", exc_info=True)
            raise
        finally:
            for msg in sources:
                await clear_reaction(msg)

    async def _build_and_submit(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        items: list[ForwardItem],
        sources: list[Message],
        trigger: TriggerPayload | None,
    ) -> None:
        app: AppContext = context.application.bot_data["app"]

        error = await validate_prompt_request(app, user_id)
        if error:
            await context.bot.send_message(chat_id=user_id, text=error)
            async with self._lock:
                if user_id not in self._buffers:
                    self._buffers[user_id] = _UserBuffer(
                        user_id=user_id,
                        items=items,
                        source_messages=sources,
                    )
            return

        blocks: list[str] = []
        images: list[SDKImage] = []

        for item in items:
            if item.kind == "text":
                msg = item.messages[0]
                blocks.append(format_forward_text_block(msg, msg.text or ""))
            elif item.kind == "photo":
                msg = item.messages[0]
                blocks.append(
                    format_forward_text_block(msg, build_prompt_text(msg.caption))
                )
                try:
                    images.append(await download_message_as_sdk_image(msg))
                except (UnsupportedImageError, TelegramDownloadError):
                    blocks.append(format_forward_text_block(msg, "(image unavailable)"))
            elif item.kind == "album":
                msg = item.messages[0]
                blocks.append(
                    format_forward_text_block(
                        msg,
                        build_prompt_text(extract_group_caption(item.messages)),
                    )
                )
                for msg in item.messages:
                    if not message_has_image(msg):
                        continue
                    try:
                        images.append(await download_message_as_sdk_image(msg))
                    except (UnsupportedImageError, TelegramDownloadError):
                        logger.debug("Skip album image", exc_info=True)
            elif item.kind == "voice":
                msg = item.messages[0]
                text = await self._transcribe_voice(app, msg)
                if text:
                    blocks.append(format_forward_text_block(msg, f"[Voice]\n{text}"))
                else:
                    blocks.append(format_forward_text_block(msg, "[Voice — empty]"))
            elif item.kind == "document":
                msg = item.messages[0]
                try:
                    filename, text, _ = await extract_message_document_text(
                        msg,
                        max_bytes=self._document_max_bytes,
                        max_chars=self._document_max_chars,
                    )
                    blocks.append(
                        format_forward_text_block(msg, f"[Document: {filename}]\n{text}")
                    )
                except DocumentTooLargeError:
                    blocks.append(
                        format_forward_text_block(msg, "[Document — file too large]")
                    )
                except (DocumentEmptyError, UnsupportedDocumentError):
                    blocks.append(
                        format_forward_text_block(msg, "[Document — no extractable text]")
                    )
            elif item.kind == "unsupported":
                msg = item.messages[0]
                kind = _unsupported_label(msg)
                blocks.append(format_forward_text_block(msg, f"[Skipped: {kind}]"))

        trigger_text: str | None = None
        if trigger is not None:
            if trigger.text:
                trigger_text = trigger.text.strip()
            elif trigger.voice_message is not None:
                trigger_text = await self._transcribe_voice(app, trigger.voice_message)
                if not trigger_text:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🎤 Не удалось распознать голосовое. Пересылки сохранены — повторите вопрос.",
                    )
                    async with self._lock:
                        self._buffers[user_id] = _UserBuffer(
                            user_id=user_id,
                            items=items,
                            source_messages=sources,
                        )
                    return

        if trigger_text:
            blocks.append(format_user_text_block(trigger_text))
        elif not blocks:
            return
        else:
            blocks.append(forward_context_default_prompt())

        prompt = join_prompt_blocks(blocks)
        if len(images) > self._photo_max_count:
            await context.bot.send_message(
                chat_id=user_id,
                text=photo_too_many(len(images), self._photo_max_count),
            )
            return

        if trigger and trigger.voice_message is not None:
            app.remember_user_message(user_id, trigger.voice_message.message_id or 0)
        elif trigger and trigger.message_id is not None:
            app.remember_user_message(user_id, trigger.message_id)
        elif sources:
            app.remember_user_message(user_id, sources[-1].message_id or 0)

        info = await submit_user_prompt(
            context=context,
            user_id=user_id,
            prompt=prompt,
            images=images or None,
            notify_queue_full=False,
        )
        if info.result == SubmitResult.REJECTED:
            await context.bot.send_message(chat_id=user_id, text=queue_full_keep_buffer())
            async with self._lock:
                self._buffers[user_id] = _UserBuffer(
                    user_id=user_id,
                    items=items,
                    source_messages=sources,
                )

    async def _transcribe_voice(self, app: AppContext, message: Message) -> str | None:
        if message.voice is None:
            return None
        tmp_path: Path | None = None
        try:
            tg_file = await message.voice.get_file()
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            await tg_file.download_to_drive(custom_path=str(tmp_path))
            return await app.transcription.transcribe_file(tmp_path)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def _classify_message(self, message: Message) -> ForwardItemKind:
        if message.voice:
            return "voice"
        if message_has_image(message):
            return "photo"
        if is_supported_document_message(message):
            return "document"
        if message.text:
            return "text"
        return "unsupported"

    def _ensure_buffer_locked(self, user_id: int) -> _UserBuffer:
        buf = self._buffers.get(user_id)
        if buf is None:
            buf = _UserBuffer(user_id=user_id)
            self._buffers[user_id] = buf
        return buf

    def _schedule_timeout_locked(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        buf: _UserBuffer,
    ) -> None:
        if buf.flush_task is not None:
            buf.flush_task.cancel()
        buf.flush_task = asyncio.create_task(
            self._delayed_timeout_flush(context, buf.user_id),
            name=f"forward_timeout_{buf.user_id}",
        )

    async def _delayed_timeout_flush(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
    ) -> None:
        try:
            await asyncio.sleep(self._timeout_sec)
            await self._timeout_flush(context, user_id)
        except asyncio.CancelledError:
            raise

    async def _update_hint(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
    ) -> None:
        async with self._lock:
            buf = self._buffers.get(user_id)
            if buf is None:
                return
            await self._update_hint_locked(context, buf)

    async def _update_hint_locked(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        buf: _UserBuffer,
    ) -> None:
        count = len(buf.items)
        if count >= self._max_items:
            text = forward_buffer_full(self._max_items)
        elif count <= 1:
            text = forward_context_hint(int(self._timeout_sec))
        else:
            text = forward_context_hint_count(count, int(self._timeout_sec))

        try:
            if buf.hint_message_id and buf.hint_chat_id:
                await context.bot.edit_message_text(
                    chat_id=buf.hint_chat_id,
                    message_id=buf.hint_message_id,
                    text=text,
                )
            else:
                sent = await context.bot.send_message(chat_id=buf.user_id, text=text)
                buf.hint_chat_id = sent.chat_id
                buf.hint_message_id = sent.message_id
        except BadRequest:
            logger.debug("Could not update forward hint", exc_info=True)

    async def _delete_hint(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        buf: _UserBuffer | None,
    ) -> None:
        if buf is None:
            return
        await self._delete_hint_by_id(context, buf.hint_chat_id, buf.hint_message_id)

    async def _delete_hint_by_id(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int | None,
        message_id: int | None,
    ) -> None:
        """Delete only the bot's forward-hint message — never a user message."""
        if chat_id is None or message_id is None:
            return
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except BadRequest:
            pass


def _unsupported_label(message: Message) -> str:
    if message.video:
        return "video"
    if message.sticker:
        return "sticker"
    if message.document:
        return "document"
    if message.audio:
        return "audio"
    return "attachment"


def get_forward_context_buffer(context: ContextTypes.DEFAULT_TYPE) -> ForwardContextBuffer:
    collector = context.application.bot_data.get(_BUFFER_KEY)
    if collector is None:
        raise RuntimeError("ForwardContextBuffer not initialized")
    return collector


def init_forward_context_buffer(application) -> None:
    app: AppContext = application.bot_data["app"]
    settings = app.settings
    application.bot_data[_BUFFER_KEY] = ForwardContextBuffer(
        timeout_sec=settings.forward_context_timeout_sec,
        max_items=settings.forward_context_max_items,
        photo_max_count=settings.photo_max_count,
        document_max_chars=settings.document_max_chars,
        document_max_bytes=settings.document_max_bytes,
    )


async def clear_forward_context(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> int:
    buffer = get_forward_context_buffer(context)
    return await buffer.clear(context, user_id)
