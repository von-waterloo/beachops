"""Tests for Telegram image helpers."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import NetworkError, TimedOut

from beachops.config.settings import CURSOR_MAX_IMAGES_PER_PROMPT, DEFAULT_PHOTO_MAX_COUNT
from beachops.services.telegram_images import (
    TelegramDownloadError,
    build_prompt_text,
    download_telegram_image,
    is_supported_image_mime,
    limit_sdk_images,
)
from beachops.services.ui_copy import photo_default_prompt


class _FakeSDKImage:
    pass


def test_is_supported_image_mime_allows_raster():
    assert is_supported_image_mime("image/png")
    assert is_supported_image_mime("image/jpeg")
    assert is_supported_image_mime("image/webp")


def test_is_supported_image_mime_rejects_svg_and_non_image():
    assert not is_supported_image_mime("image/svg+xml")
    assert not is_supported_image_mime("application/pdf")
    assert not is_supported_image_mime(None)
    assert not is_supported_image_mime("")


def test_build_prompt_text_uses_caption():
    assert build_prompt_text("  fix bug  ") == "fix bug"


def test_build_prompt_text_default_without_caption():
    assert build_prompt_text(None) == photo_default_prompt()
    assert build_prompt_text("   ") == photo_default_prompt()


def test_limit_sdk_images_truncates():
    images = [_FakeSDKImage(), _FakeSDKImage(), _FakeSDKImage()]  # type: ignore[list-item]
    limited, dropped = limit_sdk_images(images, max_count=2)  # type: ignore[arg-type]
    assert len(limited) == 2
    assert dropped == 1


def test_limit_sdk_images_no_op_when_within_limit():
    images = [_FakeSDKImage()]  # type: ignore[list-item]
    limited, dropped = limit_sdk_images(images, max_count=DEFAULT_PHOTO_MAX_COUNT)  # type: ignore[arg-type]
    assert len(limited) == 1
    assert dropped == 0


def test_cursor_image_limits():
    assert DEFAULT_PHOTO_MAX_COUNT == 5
    assert CURSOR_MAX_IMAGES_PER_PROMPT == 5


def _photo_message(*, file_id: str = "file-1") -> SimpleNamespace:
    photo = SimpleNamespace(file_id=file_id)
    bot = SimpleNamespace(get_file=AsyncMock())
    return SimpleNamespace(
        photo=[photo],
        document=None,
        get_bot=lambda: bot,
    )


@pytest.mark.asyncio
async def test_download_telegram_image_retries_on_timeout() -> None:
    message = _photo_message()
    attempts = {"download": 0}

    async def download_side_effect(*, out: BytesIO, **_kwargs: object) -> None:
        attempts["download"] += 1
        if attempts["download"] == 1:
            raise TimedOut("timed out")
        out.write(b"png-bytes")

    tg_file = SimpleNamespace(
        download_to_memory=AsyncMock(side_effect=download_side_effect)
    )
    message.get_bot().get_file = AsyncMock(return_value=tg_file)

    data, mime, filename = await download_telegram_image(
        message,  # type: ignore[arg-type]
        retries=2,
        retry_delay_sec=0.01,
    )
    assert data == b"png-bytes"
    assert mime == "image/jpeg"
    assert filename == "photo.jpg"
    assert message.get_bot().get_file.await_count == 2


@pytest.mark.asyncio
async def test_download_telegram_image_raises_after_retries() -> None:
    message = _photo_message()
    message.get_bot().get_file = AsyncMock(side_effect=NetworkError("bad gateway"))

    with pytest.raises(TelegramDownloadError):
        await download_telegram_image(
            message,  # type: ignore[arg-type]
            retries=2,
            retry_delay_sec=0.01,
        )
    assert message.get_bot().get_file.await_count == 2
