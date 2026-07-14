"""Tests for shared Telegram file download helper."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import TimedOut

from beachops.services.telegram_download import (
    TelegramFileDownloadError,
    download_telegram_file_bytes,
)


@pytest.mark.asyncio
async def test_download_telegram_file_bytes_retries() -> None:
    attempts = {"n": 0}

    async def download_side_effect(*, out: BytesIO, **_kwargs: object) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TimedOut("slow")
        out.write(b"ok-bytes")

    tg_file = SimpleNamespace(download_to_memory=AsyncMock(side_effect=download_side_effect))
    bot = SimpleNamespace(get_file=AsyncMock(return_value=tg_file))

    data = await download_telegram_file_bytes(
        bot,
        "file-1",
        retries=2,
        retry_delay_sec=0.01,
    )
    assert data == b"ok-bytes"
    assert bot.get_file.await_count == 2


@pytest.mark.asyncio
async def test_download_telegram_file_bytes_raises_after_retries() -> None:
    bot = SimpleNamespace(get_file=AsyncMock(side_effect=TimedOut("still slow")))
    with pytest.raises(TelegramFileDownloadError):
        await download_telegram_file_bytes(
            bot,
            "file-1",
            retries=2,
            retry_delay_sec=0.01,
        )
    assert bot.get_file.await_count == 2
