"""Download Telegram photos/documents and build Cursor SDK images."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from cursor_sdk import SDKImage
from telegram import Message
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.ui_copy import photo_default_prompt

logger = logging.getLogger(__name__)

_COLLECTOR_KEY = "media_group_collector"
_UNSUPPORTED_MIME = frozenset({"image/svg+xml"})
_MAX_WEB_IMAGE_BYTES = 4 * 1024 * 1024
_MAX_WEB_IMAGES_TOTAL_BYTES = 12 * 1024 * 1024
_MAX_WEB_IMAGES = 5


class UnsupportedImageError(Exception):
    """Raised when a message has no supported raster image."""


class WebImageError(ValueError):
    """Invalid image payload from Mini App / API."""


def is_supported_image_mime(mime_type: str | None) -> bool:
    if not mime_type:
        return False
    normalized = mime_type.strip().lower()
    if normalized in _UNSUPPORTED_MIME:
        return False
    return normalized.startswith("image/")


def build_prompt_text(caption: str | None) -> str:
    text = (caption or "").strip()
    return text if text else photo_default_prompt()


def bytes_to_sdk_image(data: bytes, mime_type: str) -> SDKImage:
    return SDKImage.from_data(data, mime_type)


def limit_sdk_images(
    images: Sequence[SDKImage],
    *,
    max_count: int,
) -> tuple[list[SDKImage], int]:
    """Return capped list and count of dropped images."""
    items = list(images)
    if len(items) <= max_count:
        return items, 0
    dropped = len(items) - max_count
    return items[:max_count], dropped


def encode_images_for_payload(
    items: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Validate Mini App image payloads and return serializable ``{mime, b64}`` list."""
    if not items:
        return []
    if len(items) > _MAX_WEB_IMAGES:
        raise WebImageError(f"Слишком много изображений (макс. {_MAX_WEB_IMAGES})")

    encoded: list[dict[str, str]] = []
    total = 0
    for index, item in enumerate(items):
        mime = str(item.get("mimeType") or item.get("mime") or "").strip().lower()
        raw_b64 = str(item.get("data") or item.get("b64") or "").strip()
        if raw_b64.startswith("data:") and "," in raw_b64:
            header, raw_b64 = raw_b64.split(",", 1)
            if ";base64" not in header.lower():
                raise WebImageError(f"Изображение #{index + 1}: нужен base64 data URL")
            if ":" in header:
                declared = header.split(":", 1)[1].split(";", 1)[0].strip().lower()
                if declared and not mime:
                    mime = declared
        if not is_supported_image_mime(mime):
            raise WebImageError(
                f"Изображение #{index + 1}: поддерживаются PNG, JPEG, WebP, GIF"
            )
        try:
            data = base64.b64decode(raw_b64, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise WebImageError(f"Изображение #{index + 1}: битый base64") from exc
        if not data:
            raise WebImageError(f"Изображение #{index + 1}: пустой файл")
        if len(data) > _MAX_WEB_IMAGE_BYTES:
            raise WebImageError(
                f"Изображение #{index + 1}: больше "
                f"{_MAX_WEB_IMAGE_BYTES // (1024 * 1024)} МБ"
            )
        total += len(data)
        if total > _MAX_WEB_IMAGES_TOTAL_BYTES:
            raise WebImageError("Суммарный размер скринов слишком большой")
        encoded.append(
            {
                "mime": mime,
                "b64": base64.b64encode(data).decode("ascii"),
            }
        )
    return encoded


def decode_payload_images(raw: object) -> list[SDKImage]:
    """Rebuild SDK images from encrypted job payload."""
    if not raw:
        return []
    if not isinstance(raw, list):
        raise WebImageError("invalid images payload")
    images: list[SDKImage] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        mime = str(item.get("mime") or item.get("mimeType") or "").strip().lower()
        b64 = str(item.get("b64") or item.get("data") or "").strip()
        if not is_supported_image_mime(mime) or not b64:
            continue
        try:
            data = base64.b64decode(b64, validate=False)
        except (binascii.Error, ValueError):
            continue
        if data:
            images.append(bytes_to_sdk_image(data, mime))
    return images


def _guess_photo_mime(message: Message) -> str:
    if message.document and message.document.mime_type:
        return message.document.mime_type
    return "image/jpeg"


def _image_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and is_supported_image_mime(message.document.mime_type):
        return message.document.file_id
    return None


def message_has_image(message: Message) -> bool:
    if message.photo:
        return True
    if message.document:
        return is_supported_image_mime(message.document.mime_type)
    return False


async def download_telegram_image(
    message: Message,
) -> tuple[bytes, str, str]:
    """Download raster image bytes from a Telegram message."""
    file_id = _image_file_id(message)
    if file_id is None:
        raise UnsupportedImageError("no supported image in message")

    mime_type = _guess_photo_mime(message)
    if not is_supported_image_mime(mime_type):
        raise UnsupportedImageError(f"unsupported mime: {mime_type}")

    tg_file = await message.get_bot().get_file(file_id)
    buffer = BytesIO()
    await tg_file.download_to_memory(out=buffer)
    data = buffer.getvalue()
    if not data:
        raise UnsupportedImageError("empty image download")

    filename = message.document.file_name if message.document else "photo.jpg"
    return data, mime_type, filename


async def download_message_as_sdk_image(message: Message) -> SDKImage:
    data, mime_type, _ = await download_telegram_image(message)
    return bytes_to_sdk_image(data, mime_type)


def extract_group_caption(messages: Sequence[Message]) -> str | None:
    for msg in messages:
        if msg.caption and msg.caption.strip():
            return msg.caption
    return None


@dataclass
class _MediaGroupBuffer:
    user_id: int
    messages: list[Message] = field(default_factory=list)
    flush_task: asyncio.Task[None] | None = None


class MediaGroupCollector:
    """Buffers Telegram album messages and flushes after a short delay."""

    def __init__(
        self,
        *,
        delay_sec: float,
        max_count: int,
        on_flush: Callable[[int, list[Message]], Awaitable[None]],
    ) -> None:
        self._delay_sec = delay_sec
        self._max_count = max_count
        self._on_flush = on_flush
        self._buffers: dict[str, _MediaGroupBuffer] = {}
        self._processed: set[str] = set()
        self._lock = asyncio.Lock()

    async def add(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        user_id: int,
        message: Message,
    ) -> bool:
        """Buffer an album message. Returns True if buffered (caller should stop)."""
        group_id = message.media_group_id
        if not group_id:
            return False

        async with self._lock:
            if group_id in self._processed:
                return True

            buf = self._buffers.get(group_id)
            if buf is None:
                buf = _MediaGroupBuffer(user_id=user_id)
                self._buffers[group_id] = buf

            if message.message_id not in {m.message_id for m in buf.messages}:
                buf.messages.append(message)

            if buf.flush_task is not None:
                buf.flush_task.cancel()

            buf.flush_task = asyncio.create_task(
                self._delayed_flush(context, group_id),
                name=f"media_group_flush_{group_id}",
            )
        return True

    async def _delayed_flush(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        group_id: str,
    ) -> None:
        try:
            await asyncio.sleep(self._delay_sec)
            await self._flush_group(context, group_id)
        except asyncio.CancelledError:
            raise

    async def _flush_group(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        group_id: str,
    ) -> None:
        async with self._lock:
            buf = self._buffers.pop(group_id, None)
            if buf is None or group_id in self._processed:
                return
            self._processed.add(group_id)
            messages = sorted(buf.messages, key=lambda m: m.message_id or 0)
            user_id = buf.user_id

        try:
            await self._on_flush(user_id, messages)
        except Exception:
            logger.exception("Media group flush failed for %s", group_id)
        finally:
            async with self._lock:
                self._processed.discard(group_id)


def get_media_group_collector(context: ContextTypes.DEFAULT_TYPE) -> MediaGroupCollector:
    collector = context.application.bot_data.get(_COLLECTOR_KEY)
    if collector is None:
        raise RuntimeError("MediaGroupCollector not initialized")
    return collector


def init_media_group_collector(
    application,
    *,
    on_flush: Callable[[int, list[Message]], Awaitable[None]],
) -> None:
    app: AppContext = application.bot_data["app"]
    settings = app.settings
    application.bot_data[_COLLECTOR_KEY] = MediaGroupCollector(
        delay_sec=settings.media_group_delay_sec,
        max_count=settings.photo_max_count,
        on_flush=on_flush,
    )
