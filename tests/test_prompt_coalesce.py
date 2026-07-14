"""Tests for prompt coalesce helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from beachops.services.prompt_coalesce import PromptCoalesceBuffer, _compose_prompt
from beachops.services.telegram_images import TelegramDownloadError
from beachops.services.ui_copy import photo_default_prompt, photo_download_timeout


def _msg(*, message_id: int, caption: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(message_id=message_id, caption=caption)


def test_compose_prompt_prefers_text_then_unique_caption() -> None:
    photos = [_msg(message_id=1, caption="смотри скрин")]
    assert _compose_prompt(["почини баг"], photos) == "почини баг\n\nсмотри скрин"


def test_compose_prompt_dedupes_identical_text_and_caption() -> None:
    photos = [_msg(message_id=1, caption="одно и то же")]
    assert _compose_prompt(["одно и то же"], photos) == "одно и то же"


def test_compose_prompt_caption_only() -> None:
    photos = [_msg(message_id=2, caption="только подпись")]
    assert _compose_prompt([], photos) == "только подпись"


def test_compose_prompt_default_without_text() -> None:
    assert _compose_prompt([], []) == photo_default_prompt()


def test_coalesce_has_pending_tracks_content() -> None:
    buf = PromptCoalesceBuffer(delay_sec=5.0, max_images=20)
    assert not buf.has_pending(1)
    buf._pending[1] = buf._ensure_locked(1)
    buf._pending[1].texts.append("hi")
    assert buf.has_pending(1)


@pytest.mark.asyncio
async def test_flush_shows_timeout_copy_when_all_downloads_fail(monkeypatch) -> None:
    buf = PromptCoalesceBuffer(delay_sec=0.0, max_images=5)
    photo = MagicMock()
    photo.message_id = 11
    photo.caption = None
    status = MagicMock(edit_text=AsyncMock(), delete=AsyncMock())
    photo.reply_text = AsyncMock(side_effect=[status, MagicMock()])

    bot = MagicMock()
    bot.send_message = AsyncMock()
    context = MagicMock()
    context.bot = bot
    context.application.bot_data = {
        "app": SimpleNamespace(
            settings=SimpleNamespace(prompt_max_chars=8000, photo_max_count=5),
            remember_user_message=lambda *_a, **_k: None,
        )
    }

    pending = buf._ensure_locked(42)
    pending.photo_messages = [photo]
    buf._pending[42] = pending

    monkeypatch.setattr(
        "beachops.services.prompt_coalesce.validate_prompt_request",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "beachops.services.prompt_coalesce.download_message_as_sdk_image",
        AsyncMock(side_effect=TelegramDownloadError("timed out")),
    )
    monkeypatch.setattr(
        "beachops.services.prompt_coalesce.submit_user_prompt",
        AsyncMock(),
    )

    class _NoAnim:
        def __init__(self, *_a, **_k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

    monkeypatch.setattr(
        "beachops.services.prompt_coalesce.AnimatedStatus",
        _NoAnim,
    )
    monkeypatch.setattr(
        "beachops.services.prompt_coalesce.initial_status_text",
        lambda **_k: "loading",
    )

    await buf._flush_user(context, 42)

    status.delete.assert_awaited()
    assert photo.reply_text.await_count == 2
    assert photo.reply_text.await_args_list[1].args[0] == photo_download_timeout()
    bot.send_message.assert_not_awaited()
