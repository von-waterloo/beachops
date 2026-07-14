"""Shared Telegram Bot API file download with retries and timeouts."""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Any

from telegram.error import NetworkError, RetryAfter, TimedOut

from beachops.config.settings import get_settings

logger = logging.getLogger(__name__)


class TelegramFileDownloadError(Exception):
    """Raised when Telegram file download fails after retries."""


async def download_telegram_file_bytes(
    bot: Any,
    file_id: str,
    *,
    retries: int | None = None,
    retry_delay_sec: float | None = None,
) -> bytes:
    """Download file bytes by ``file_id`` with retries and explicit timeouts."""
    settings = get_settings() if retries is None or retry_delay_sec is None else None
    max_attempts = (
        retries
        if retries is not None
        else settings.telegram_download_retries  # type: ignore[union-attr]
    )
    delay = (
        retry_delay_sec
        if retry_delay_sec is not None
        else settings.telegram_download_retry_delay_sec  # type: ignore[union-attr]
    )
    if settings is not None:
        file_timeouts = {
            "read_timeout": settings.telegram_read_timeout_sec,
            "write_timeout": settings.telegram_write_timeout_sec,
            "connect_timeout": settings.telegram_connect_timeout_sec,
            "pool_timeout": settings.telegram_pool_timeout_sec,
        }
    else:
        file_timeouts = {
            "read_timeout": 90.0,
            "write_timeout": 90.0,
            "connect_timeout": 30.0,
            "pool_timeout": 30.0,
        }

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            tg_file = await bot.get_file(file_id, **file_timeouts)
            buffer = BytesIO()
            await tg_file.download_to_memory(out=buffer, **file_timeouts)
            data = buffer.getvalue()
            if not data:
                raise TelegramFileDownloadError("empty telegram file download")
            return data
        except TelegramFileDownloadError:
            raise
        except RetryAfter as exc:
            last_exc = exc
            wait = float(exc.retry_after) + 0.5
            logger.warning(
                "Telegram rate limit while downloading file (attempt %s/%s), wait %.1fs",
                attempt + 1,
                max_attempts,
                wait,
            )
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts:
                break
            wait = delay * (attempt + 1)
            logger.warning(
                "Telegram file download failed (attempt %s/%s): %s; retry in %.1fs",
                attempt + 1,
                max_attempts,
                exc,
                wait,
            )
            await asyncio.sleep(wait)

    raise TelegramFileDownloadError(
        "telegram file download failed"
    ) from last_exc
